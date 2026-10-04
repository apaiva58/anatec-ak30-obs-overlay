"""
scene_logic.py
==============
Decides when OBS should change scene. Pure logic: no OBS, no threads, no
Flask, so every rule can be tested against real captured frames
(tests/test_scene_logic.py).

The rules, in short
-------------------
- A period ends when the clock RUNS DOWN to 0:00 and the console drops to
  minute mode. Only periods listed in `stats_after` (default: 2, the
  halftime) get the stats scene, a short delay after the buzzer.
- Going back to the court is NOT decided from the clock. Scorers run the
  break clock in different ways and advance the period at different
  moments, so the clock cannot tell a break countdown from play. The
  return is triggered by play evidence instead: a goal, foul or timeout in
  FOYS for a later period, or a score, team-foul or timeout counter going
  up on the console. The operator can also just switch in OBS; that is
  accepted and nothing fights it.
- A buzzer only counts if the period it ends has seen play, and only once
  per period. That rejects the end of a break countdown.
- The end of the match is not a buzzer either. The desk finalises the
  match some minutes later; when the FOYS status turns Final, the final
  scene goes on air.
- `prompt` holds a one-line message for the operator that says what
  happens next.

What the real console does at the end of a period (capture 2026-04-23):

    ... 0:00.3   0:00.1   0:00 (minute mode, buzzer flag on)   0:00 ...

The tenths display stops at 0:00.1 and the console drops back to plain
0:00 with the tenths absent. It never shows 0:00.0 at the buzzer. Two
triggers that look natural are both wrong:

  seconds == 0   fires while up to 0.9 s of play remain, and also when
                 the clock is merely stopped inside the last second
                 (the capture has the clock parked at 0:00.6 for 14 s)
  tenths == 0    can fire a second early too: one pass of the same
                 capture has a single stray 0:00.0 frame at the 1 s
                 rollover, between 0:01.1 and 0:00.8

The reliable marker is a clock that was RUNNING and then lands on 0:00
in minute mode. A clock set to 0:00 by hand did not run, so it does not
count.
"""

from collections import namedtuple
from dataclasses import dataclass
from typing import Optional

# FOYS numbers its periods 14, 15, 16, 17 for quarters 1 to 4 (verified on
# match 501153), so a FOYS periodId is 13 + the console's period number.
FOYS_PERIOD_BASE = 13

# Operator-facing messages (Dutch, shown on the status dock). Edit freely.
MSG_HALFTIME = "Rust. Naar WIDE bij start periode {next}."
MSG_WAIT_FINAL = "Einde periode {period}: wacht op afsluiten in FOYS."
MSG_FINAL = "Wedstrijd afgesloten."

Action = namedtuple("Action", "scene reason")


def parse_periods(text, default=(2,)):
    """'1,2,3' -> {1, 2, 3}. Anything that is not a positive number is
    ignored; an empty result falls back to `default`."""
    out = set()
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            out.add(int(part))
    return out or set(default)


def parse_seconds(text, default):
    try:
        value = float(text)
        return value if value >= 0 else default
    except (TypeError, ValueError):
        return default


class BuzzerDetector:
    """
    Reports the one sample on which the clock lands on 0:00 in minute mode
    after having run. Also knows whether the clock is running again, which
    the director uses to cancel a switch that has not happened yet.

    max_step     tenths; the largest single downward move a running clock
                 can make between two samples (30 = 3 s). A bigger move is
                 the scorer setting the clock.
    run_gap      seconds without a step after which a run is over
    run_window   seconds within which the last step must lie for 0:00 to
                 count as "the clock ran down to zero"
    resume_steps consecutive downward steps that mean "running again"
    """

    def __init__(self, resume_steps=2, max_step=30, run_gap=3.0, run_window=5.0):
        self.resume_steps = resume_steps
        self.max_step = max_step
        self.run_gap = run_gap
        self.run_window = run_window
        self._prev_t = None
        self._last_run = None
        self._streak = 0
        self._at_zero = False

    @property
    def running_again(self):
        return self._streak >= self.resume_steps

    def _track(self, now, t):
        prev, self._prev_t = self._prev_t, t
        if prev is None:
            return
        d = prev - t
        if 0 < d <= self.max_step:
            if self._last_run is None or now - self._last_run > self.run_gap:
                self._streak = 1
            else:
                self._streak += 1
            self._last_run = now
        elif d == 0:
            if self._last_run is not None and now - self._last_run > self.run_gap:
                self._streak = 0
        else:
            # went up, or jumped down further than a running clock could
            self._streak = 0

    def update(self, now, minutes, seconds, tenths):
        if minutes is None or seconds is None:
            return False
        self._track(now, (minutes * 60 + seconds) * 10 + (tenths or 0))

        at_zero = minutes == 0 and seconds == 0 and tenths is None
        if not at_zero:
            self._at_zero = False
            return False
        if self._at_zero:                 # already reported for this stop
            return False
        self._at_zero = True
        ran = self._last_run is not None and now - self._last_run <= self.run_window
        if ran:
            self._streak = 0              # only steps after the buzzer count
        return ran


@dataclass
class Snapshot:
    """Everything the director needs at one moment."""
    now: float
    period: Optional[int] = None            # console period, None if unknown
    minutes: Optional[int] = None
    seconds: Optional[int] = None
    tenths: Optional[int] = None
    counters: Optional[tuple] = None        # console: home/guest score, fouls, timeouts
    foys_event_period: Optional[int] = None  # highest periodId with a goal, foul or timeout
    match_id: Optional[int] = None
    status: Optional[str] = None            # FOYS status: Planned, InProgress, Final
    on_air: Optional[str] = None            # scene OBS shows now, None if unknown


class _Break:
    def __init__(self, period, t, foys_base, message_only):
        self.period = period
        self.t = t                          # when the buzzer was detected
        self.foys_base = foys_base          # FOYS events at or below this are the old period
        self.message_only = message_only    # no scene was switched, only a prompt shown
        self.switched = False
        self.seen = False                   # the stats scene was seen on air


class SceneDirector:
    """
    scenes        {"court": name, "halftime": name, "final": name}
    stats_after   periods whose end puts the halftime scene on air
    stats_delay   seconds to keep the court on air after the buzzer
    quiet_s       seconds after a buzzer during which console counter
                  increases are late entries, not play
    final_period  this period and later never switch automatically
    """

    def __init__(self, scenes, stats_after=(2,), stats_delay=2.0,
                 quiet_s=30.0, final_period=4):
        self.scenes = dict(scenes)
        self.stats_after = set(stats_after)
        self.stats_delay = stats_delay
        self.quiet_s = quiet_s
        self.final_period = final_period
        self.prompt = None
        self._det = BuzzerDetector()
        self._match = (None, None)          # match id, last seen status
        self._last_period = None
        self._reset_match()

    def _reset_match(self):
        self._played = set()                # console periods that have seen play
        self._fired = set()                 # console periods whose buzzer was handled
        self._pending = None                # (due time, period): stats scene waiting for its delay
        self._break = None
        self._prev_counters = None
        self._done = False
        self.prompt = None

    # -- helpers -------------------------------------------------------

    def _switch(self, actions, s, key, reason):
        scene = self.scenes[key]
        if s.on_air != scene:
            actions.append(Action(scene, reason))

    def _clear_break(self):
        self._break = None
        self.prompt = None

    # -- steps ---------------------------------------------------------

    def _track_match(self, s, actions, notes):
        mid, st = s.match_id, s.status
        prev_mid, prev_st = self._match
        if mid is not None and prev_mid is not None and mid != prev_mid:
            self._reset_match()
            prev_st = None
        if mid is None:
            return
        if st == "Final" and prev_st not in (None, "Final") and not self._done:
            self._pending = None
            self._break = None
            self._done = True
            self.prompt = MSG_FINAL
            self._switch(actions, s, "final", "match finalised")
            notes.append("match finalised in FOYS: final scene")
        self._match = (mid, st)

    def _track_period(self, s, notes):
        """The console period going backwards means a new game started (the
        operator reset it), so forget what the last game taught us."""
        p = s.period
        if p is None:
            return
        last, self._last_period = self._last_period, p
        if last is not None and p < last:
            self._reset_match()
            notes.append(f"period went back from {last} to {p}: new game")

    def _track_evidence(self, s):
        """Records which periods have seen play. Returns True if a console
        counter went up since the last sample."""
        fp = s.foys_event_period
        if fp is not None:
            for k in range(1, fp - FOYS_PERIOD_BASE + 1):
                self._played.add(k)
        grew = False
        c = s.counters
        if c is not None:
            if self._prev_counters is not None and any(
                    a > b for a, b in zip(c, self._prev_counters)):
                grew = True
                if s.period is not None:
                    self._played.add(s.period)
            self._prev_counters = c
        return grew

    def _on_buzzer(self, s, notes):
        p = s.period
        if p not in self._played:
            notes.append(f"clock ran out in period {p} before any play in it: ignored")
            return
        if p in self._fired:
            notes.append(f"clock ran out again in period {p}: ignored (break clock)")
            return
        base = max(s.foys_event_period or 0, FOYS_PERIOD_BASE + p)
        if p in self.stats_after:
            self._pending = (s.now + self.stats_delay, p)
            self._break = _Break(p, s.now, base, message_only=False)
            self.prompt = MSG_HALFTIME.format(next=p + 1)
            notes.append(f"end of period {p}: stats scene in {self.stats_delay:g}s")
        elif p >= self.final_period:
            self._fired.add(p)
            self._break = _Break(p, s.now, base, message_only=True)
            self.prompt = MSG_WAIT_FINAL.format(period=p)
            notes.append(f"end of period {p}: waiting for the match to be finalised")
        else:
            self._fired.add(p)

    def _run_pending(self, s, actions, notes):
        if self._pending is None:
            return
        due, p = self._pending
        if self._det.running_again:
            self._pending = None
            self._clear_break()
            notes.append("clock running again: stats scene cancelled")
            return
        if s.now >= due:
            self._pending = None
            self._fired.add(p)
            self._switch(actions, s, "halftime", f"end of period {p}")
            if self._break is not None:
                self._break.switched = True

    def _run_break(self, s, grew, actions, notes):
        b = self._break
        if b is None or self._pending is not None:
            return

        # The operator moved off the stats scene by hand: accept it.
        if b.switched and not b.message_only:
            if s.on_air == self.scenes["halftime"]:
                b.seen = True
            elif b.seen and s.on_air is not None:
                self._clear_break()
                notes.append("scene changed by hand: prompt cleared")
                return

        fp = s.foys_event_period
        if fp is not None and fp > b.foys_base:
            why = f"FOYS event in a later period (periodId {fp})"
        elif grew and s.now >= b.t + self.quiet_s:
            why = "console counter went up"
        else:
            return

        if not b.message_only and s.on_air in (None, self.scenes["halftime"]):
            self._switch(actions, s, "court", "play resumed")
        self._clear_break()
        notes.append(f"play resumed ({why})")

    # -- entry point ---------------------------------------------------

    def update(self, s):
        """Feed one snapshot. Returns (actions, notes): a list of Action(scene,
        reason) to carry out, and short lines worth logging."""
        actions, notes = [], []
        self._track_match(s, actions, notes)
        self._track_period(s, notes)
        if self._done:
            return actions, notes
        grew = self._track_evidence(s)
        buzzer = self._det.update(s.now, s.minutes, s.seconds, s.tenths)
        if buzzer and s.period is not None:
            self._on_buzzer(s, notes)
        self._run_pending(s, actions, notes)
        self._run_break(s, grew, actions, notes)
        return actions, notes
