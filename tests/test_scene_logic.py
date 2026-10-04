"""
Tests for scoreboard/scene_logic.py and scoreboard/scene_control.py.

Run from the repo root:
    python3 tests/test_scene_logic.py

No pytest needed. The buzzer tests replay REAL frames from the capture of
2026-04-23 (anatec_capture_20260423_182910.txt, period 2), embedded here as
data because the capture files are not in git.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scoreboard"))

from scene_logic import (BuzzerDetector, SceneDirector, Snapshot, parse_periods,  # noqa: E402
                         MSG_FINAL, MSG_HALFTIME, MSG_WAIT_FINAL)
from scene_control import SceneController, DryObs  # noqa: E402

FPS = 10.9      # frames per second on the wire (2400 baud, 22 bytes a frame)
DT = 0.25       # the controller's sample interval
DELAY = 2.0     # stats_delay used throughout

COURT = "Scène 2: WIDE Overlay"
STATS_SCENE = "Scène 4: STATS"
BOX = "Scène 1: BOX overlay"
SCENES = {"court": COURT, "halftime": STATS_SCENE, "final": STATS_SCENE}

# (frame number, minutes, seconds, tenths); tenths None = minute mode.
RUN_A = [
    (7502, 0, 1, 9), (7503, 0, 1, 8), (7504, 0, 1, 6), (7505, 0, 1, 4),
    (7506, 0, 1, 3), (7507, 0, 1, 1), (7508, 0, 0, 9), (7509, 0, 0, 8),
    (7510, 0, 0, 6), (7511, 0, 0, 4), (7512, 0, 0, 3), (7513, 0, 0, 1),
    (7514, 0, 0, None),   # buzzer: minute mode, never 0:00.0
    (7530, 0, 0, None),
]
T_END_A = 7514 / FPS

# A messier pass of the same capture: the clock parks at 0:01.4 for 122
# frames, frame 8429 is a single stray 0:00.0 between 0:01.1 and 0:00.8, and
# the clock parks at 0:00.6 for 155 frames (14 s) before running out.
RUN_B = [
    (8302, 0, 1, 9), (8303, 0, 1, 7), (8304, 0, 1, 5), (8305, 0, 1, 4),
    (8427, 0, 1, 3), (8428, 0, 1, 1),
    (8429, 0, 0, 0),      # the glitch
    (8430, 0, 0, 8), (8431, 0, 0, 6),
    (8586, 0, 0, 4), (8587, 0, 0, 3), (8588, 0, 0, 1),
    (8589, 0, 0, None),   # the real end
    (8605, 0, 0, None),
]
T_END_B = 8589 / FPS


# -- helpers for the buzzer detector --------------------------------------

def real_timeline(frames, period):
    return [(n / FPS, period, m, s, t) for n, m, s, t in frames]


def sample(timeline, phase=0.0, tail=10.0):
    """Sample a timeline every DT seconds, holding the last value."""
    now = timeline[0][0] - 1.0 + phase
    end = timeline[-1][0] + tail
    i, cur = 0, None
    while now <= end:
        while i < len(timeline) and timeline[i][0] <= now:
            cur = timeline[i]
            i += 1
        if cur is not None:
            yield now, cur[1], cur[2], cur[3], cur[4]
        now += DT


def hits(samples):
    det = BuzzerDetector()
    return [now for now, _, m, s, t in samples if det.update(now, m, s, t)]


class Trace:
    """Synthetic clock samples at DT intervals."""

    def __init__(self, start=100.0):
        self.now, self.samples = start, []

    def add(self, m, s, t, seconds):
        for _ in range(max(1, round(seconds / DT))):
            self.samples.append((self.now, 0, m, s, t))
            self.now += DT
        return self


# -- helpers for the director ---------------------------------------------

class Rig:
    """Drives a SceneDirector the way the controller does: one snapshot per
    DT, and a switch the director asks for is applied to on_air."""

    def __init__(self, scenes=SCENES, **kw):
        self.d = SceneDirector(scenes, stats_delay=DELAY, **kw)
        self.now = self.t0 = 1000.0
        self.f = dict(period=1, minutes=10, seconds=0, tenths=None,
                      counters=(0, 0, 0, 0, 0, 0), foys=None,
                      match_id=None, status=None, on_air=COURT)
        self.switches, self.notes = [], []     # (seconds since start, ...)
        self.buzzer_at = None

    def set(self, **kw):
        self.f.update(kw)

    def score(self, idx=0, by=2):
        c = list(self.f["counters"])
        c[idx] += by
        self.f["counters"] = tuple(c)

    def tick(self):
        f = self.f
        snap = Snapshot(now=self.now, period=f["period"], minutes=f["minutes"],
                        seconds=f["seconds"], tenths=f["tenths"],
                        counters=f["counters"], foys_event_period=f["foys"],
                        match_id=f["match_id"], status=f["status"], on_air=f["on_air"])
        actions, notes = self.d.update(snap)
        for a in actions:
            self.switches.append((self.now - self.t0, a.scene))
            f["on_air"] = a.scene
        for n in notes:
            self.notes.append((self.now - self.t0, n))
        self.now += DT

    def run(self, seconds):
        for _ in range(max(1, round(seconds / DT))):
            self.tick()

    def play(self, period, seconds=1.0):
        """Some play in a period: the console score goes up."""
        self.set(period=period, minutes=5, seconds=0, tenths=None)
        self.tick()
        self.score(0, 2)
        self.tick()
        self.run(seconds)

    def end(self, period, hold=1.0):
        """The clock runs down to the console's 0:00."""
        self.set(period=period)
        for tenths in (5, 3, 1):
            self.set(minutes=0, seconds=0, tenths=tenths)
            self.tick()
        self.set(minutes=0, seconds=0, tenths=None)
        self.buzzer_at = self.now - self.t0
        self.run(hold)

    def scenes(self):
        return [s for _, s in self.switches]

    def has_note(self, text):
        return any(text in n for _, n in self.notes)


def halftime(r, foys=None):
    """Play in periods 1 and 2, end period 2, wait for the stats scene."""
    r.set(foys=foys)
    r.play(1)
    r.end(1)
    r.play(2)
    r.end(2, hold=DELAY + 1.0)


# -- buzzer detector on real frames ----------------------------------------

def test_real_end_of_period_reported_once_at_the_buzzer_frame():
    for k in range(25):
        h = hits(sample(real_timeline(RUN_A, 2), phase=k * 0.01))
        assert len(h) == 1, f"phase {k}: {h}"
        assert T_END_A <= h[0] <= T_END_A + DT + 1e-9, f"phase {k}: {h[0] - T_END_A:+.2f}s"


def test_real_capture_with_glitch_and_long_stops():
    glitch_seen = 0
    for k in range(25):
        samples = list(sample(real_timeline(RUN_B, 2), phase=k * 0.01))
        glitch_seen += any((m, s, t) == (0, 0, 0) for _, _, m, s, t in samples)
        h = hits(samples)
        assert len(h) == 1, f"phase {k}: {h}"
        assert T_END_B <= h[0] <= T_END_B + DT + 1e-9, f"phase {k}: {h[0] - T_END_B:+.2f}s"
    assert glitch_seen > 0, "no sampling phase landed on the glitch frame"


def test_clock_set_by_hand_to_zero_is_not_a_buzzer():
    tr = Trace().add(10, 0, None, 30).add(0, 0, None, 60)
    assert hits(tr.samples) == []


def test_clock_parked_in_the_last_second_is_not_a_buzzer():
    tr = Trace().add(0, 0, 5, DT).add(0, 0, 3, DT).add(0, 0, 6, 30)
    assert hits(tr.samples) == []


# -- director --------------------------------------------------------------

def test_halftime_gets_the_stats_scene_and_a_prompt():
    r = Rig()
    r.play(1)
    r.end(1, hold=DELAY + 1.0)
    assert r.switches == [], "period 1 must not switch"
    r.play(2)
    r.end(2, hold=DELAY + 1.0)
    assert r.scenes() == [STATS_SCENE]
    t = r.switches[0][0]
    assert r.buzzer_at + DELAY <= t <= r.buzzer_at + DELAY + DT + 1e-9
    assert r.d.prompt == MSG_HALFTIME.format(next=3) == "Rust. Naar WIDE bij start periode 3."


def test_periods_1_and_3_never_switch_by_default():
    r = Rig()
    for p in (1, 3):
        r.play(p)
        r.end(p, hold=DELAY + 1.0)
    assert r.switches == [] and r.d.prompt is None


def test_end_of_period_4_prompts_and_final_switches_when_foys_finalises():
    r = Rig()
    r.set(match_id=7, status="InProgress")
    r.play(4)
    r.end(4, hold=DELAY + 1.0)
    assert r.switches == []
    assert r.d.prompt == MSG_WAIT_FINAL.format(period=4)
    r.set(status="Final")
    r.run(1.0)
    assert r.scenes() == [STATS_SCENE]
    assert r.d.prompt == MSG_FINAL


def test_a_match_that_is_already_final_when_selected_does_not_switch():
    r = Rig()
    r.set(match_id=7, status="Final")
    r.run(3.0)
    assert r.switches == []
    r.set(match_id=8, status="InProgress")
    r.run(1.0)
    r.set(status="Final")
    r.run(1.0)
    assert r.scenes() == [STATS_SCENE]


def test_a_buzzer_before_any_play_in_the_period_is_ignored():
    r = Rig()
    r.end(2, hold=DELAY + 1.0)
    assert r.switches == [] and r.has_note("before any play")


def test_end_of_the_break_clock_does_not_bring_the_stats_scene_back():
    r = Rig()
    halftime(r)
    assert r.scenes() == [STATS_SCENE]
    r.set(on_air=COURT)               # operator went back to the court by hand
    r.run(1.0)
    r.end(2, hold=DELAY + 1.0)        # the break clock runs out in period 2
    assert r.scenes() == [STATS_SCENE], r.switches
    assert r.has_note("ignored (break clock)")


def test_break_clock_ending_after_the_period_was_advanced_is_ignored():
    r = Rig()
    halftime(r)
    r.set(on_air=COURT)
    r.run(1.0)
    r.set(period=3)                   # period advanced, no play in 3 yet
    r.end(3, hold=DELAY + 1.0)
    assert r.scenes() == [STATS_SCENE]
    assert r.has_note("before any play")


def test_a_late_foys_entry_for_the_old_period_is_not_play_but_the_next_period_is():
    r = Rig()
    halftime(r, foys=15)              # FOYS has events up to period 2 (id 15)
    assert r.scenes() == [STATS_SCENE]
    r.set(foys=15)
    r.run(5.0)
    assert r.scenes() == [STATS_SCENE], "late period-2 entry must not count"
    r.set(foys=16)                    # first event of period 3
    r.run(1.0)
    assert r.scenes() == [STATS_SCENE, COURT]
    assert r.d.prompt is None


def test_console_counters_count_as_play_only_after_the_quiet_window():
    r = Rig()
    halftime(r)
    r.run(10.0)
    r.score(0, 2)                     # a late entry for the last play
    r.run(1.0)
    assert r.scenes() == [STATS_SCENE], "inside the quiet window"
    r.run(30.0)
    r.score(1, 2)
    r.run(1.0)
    assert r.scenes() == [STATS_SCENE, COURT]


def test_console_counter_resets_are_not_play():
    r = Rig()
    r.play(1)
    r.play(2)
    r.score(2, 3)
    r.score(5, 1)                     # fouls and a timeout on the console
    r.run(1.0)
    r.end(2, hold=DELAY + 1.0)
    assert r.scenes() == [STATS_SCENE]
    r.run(40.0)
    r.set(counters=(r.f["counters"][0], r.f["counters"][1], 0, 0, 0, 0))   # the table resets fouls
    r.run(2.0)
    assert r.scenes() == [STATS_SCENE] and r.d.prompt is not None


def test_a_scene_chosen_by_hand_is_respected():
    for chosen in (COURT, BOX):
        r = Rig()
        halftime(r, foys=15)
        r.set(on_air=chosen)
        r.run(1.5)
        assert r.d.prompt is None, f"prompt must clear when {chosen!r} is picked"
        r.set(foys=16)
        r.run(1.0)
        assert r.scenes() == [STATS_SCENE], f"must not fight the operator ({chosen!r})"


def test_unknown_on_air_scene_is_treated_as_still_on_stats():
    r = Rig()
    halftime(r, foys=15)
    r.set(on_air=None)
    r.set(foys=16)
    r.run(1.0)
    assert r.scenes() == [STATS_SCENE, COURT]


def test_evidence_does_not_override_a_scene_chosen_before_stats_ever_appeared():
    # OBS never showed the stats scene (refused or down) and the operator
    # picked BOX by hand in the meantime: play evidence must not replace it.
    r = Rig()
    r.set(foys=15)
    r.play(1)
    r.end(1)
    r.play(2)
    r.end(2, hold=DELAY)
    r.tick()                          # the switch is issued on this tick
    assert r.scenes() == [STATS_SCENE]
    r.f["on_air"] = BOX               # ... but OBS is showing BOX
    r.set(foys=16)
    r.run(1.0)
    assert r.scenes() == [STATS_SCENE], r.switches


def test_clock_running_again_inside_the_delay_cancels_and_the_true_end_still_fires():
    r = Rig()
    r.play(1)
    r.play(2)
    r.set(period=2)
    for tenths in (5, 3, 1):
        r.set(minutes=0, seconds=0, tenths=tenths)
        r.tick()
    r.set(minutes=0, seconds=0, tenths=None)
    r.tick()                          # false end: arms
    r.set(minutes=0, seconds=3, tenths=None)
    r.tick()                          # corrected upward
    r.set(minutes=0, seconds=2, tenths=None)
    r.run(0.75)
    r.set(minutes=0, seconds=1, tenths=None)
    r.run(0.75)                       # two steps: cancels
    assert r.switches == [] and r.d.prompt is None and r.has_note("cancelled")
    r.set(minutes=0, seconds=0, tenths=None)
    r.run(DELAY + 1.0)                # the true end
    assert r.scenes() == [STATS_SCENE]


def test_the_console_period_going_back_starts_a_new_game():
    r = Rig()
    halftime(r)
    assert r.scenes() == [STATS_SCENE]
    r.set(on_air=COURT)
    r.set(period=1, counters=(0, 0, 0, 0, 0, 0))     # next game
    r.run(1.0)
    assert r.has_note("new game")
    r.play(1)
    r.end(1)
    r.play(2)
    r.end(2, hold=DELAY + 1.0)
    assert r.scenes() == [STATS_SCENE, STATS_SCENE]


def test_scenes_and_triggers_are_configurable():
    scenes = dict(SCENES, final="Final Stats")
    r = Rig(scenes=scenes, stats_after={1, 2, 3})
    r.set(match_id=7, status="InProgress")
    r.play(1)
    r.end(1, hold=DELAY + 1.0)
    assert r.scenes() == [STATS_SCENE], "period 1 was added to stats_after"
    r.set(status="Final")
    r.run(1.0)
    assert r.scenes() == [STATS_SCENE, "Final Stats"]


def test_parse_periods():
    assert parse_periods("1,2,3") == {1, 2, 3}
    assert parse_periods("2") == {2}
    assert parse_periods("") == {2}
    assert parse_periods("x, 2;3") == {2, 3}
    assert parse_periods("0,-1") == {2}


# -- controller with a fake OBS --------------------------------------------

class FakeObs:
    def __init__(self, scenes, start=COURT, refuse=0, up=True):
        self.names, self.scene, self.refuse, self.up = list(scenes), start, refuse, up
        self._connected, self.calls, self.error = False, [], None

    @property
    def connected(self):
        return self._connected

    def connect(self):
        if not self.up:
            self.error = "ConnectionRefusedError: [Errno 61] Connection refused"
            return False
        self._connected = True
        return True

    def drop(self):
        self._connected = False

    def _need(self):
        if not self._connected:
            raise RuntimeError("not connected")

    def scene_names(self):
        self._need()
        return list(self.names)

    def current_scene(self):
        self._need()
        return self.scene

    def switch(self, name):
        self._need()
        self.calls.append(name)
        if self.refuse > 0:
            self.refuse -= 1
            raise RuntimeError("refused")
        self.scene = name


def new_state():
    return {"selected": False, "match_id": None, "status": "Planned",
            "anatec_period": 0, "anatec_clock_min": 10, "anatec_clock_sec": 0,
            "anatec_clock_tenths": None, "foys_event_period": None,
            "anatec_home_score": 0, "anatec_guest_score": 0,
            "anatec_home_fouls": 0, "anatec_guest_fouls": 0,
            "anatec_home_timeouts": 0, "anatec_guest_timeouts": 0}


class Bench:
    def __init__(self, obs, scenes=SCENES, live=True):
        self.state, self.obs, self.lines = new_state(), obs, []
        self.d = SceneDirector(scenes, stats_delay=DELAY)
        self.c = SceneController(self.state, obs, self.d, scenes, live=live,
                                 log=self.lines.append)
        self.now = 5000.0

    def run(self, seconds):
        for _ in range(max(1, round(seconds / DT))):
            self.c.step(self.now)
            self.now += DT

    def clock(self, m, s, t):
        self.state.update(anatec_clock_min=m, anatec_clock_sec=s, anatec_clock_tenths=t)

    def play(self, period):
        self.state.update(anatec_period=period)
        self.clock(5, 0, None)
        self.run(DT)
        self.state["anatec_home_score"] += 2
        self.run(1.0)

    def end(self, period):
        self.state["anatec_period"] = period
        for t in (5, 3, 1):
            self.clock(0, 0, t)
            self.run(DT)
        self.clock(0, 0, None)

    def log_has(self, text):
        return any(text in line for line in self.lines)


def test_controller_retries_refused_switches_and_publishes():
    obs = FakeObs(SCENES.values(), refuse=2)
    b = Bench(obs)
    b.run(2.0)
    assert b.state["obs_available"] is True and b.state["obs_scene"] == COURT
    b.play(1)
    b.end(1)
    b.run(1.0)
    b.play(2)
    b.end(2)
    b.run(30.0)
    assert obs.calls == [STATS_SCENE] * 3, obs.calls
    assert obs.scene == STATS_SCENE and b.state["obs_scene"] == STATS_SCENE
    assert b.state["scene_prompt"] == MSG_HALFTIME.format(next=3)
    assert b.log_has("[OBS] Scene switch failed") and b.log_has("[OBS] connection lost")


def test_controller_reports_a_scene_missing_in_obs_and_does_not_drop_the_connection():
    scenes = dict(SCENES, final="Final Stats")
    obs = FakeObs([COURT, STATS_SCENE])           # "Final Stats" not created yet
    b = Bench(obs, scenes=scenes)
    b.run(2.0)
    assert b.state["obs_missing_scenes"] == ["Final Stats"]
    b.state.update(selected=True, match_id=7, status="InProgress")
    b.run(1.0)
    b.state["status"] = "Final"
    b.run(2.0)
    assert obs.calls == [] and obs.connected, "must not try, must not drop"
    assert b.log_has("no such scene in OBS")
    obs.names.append("Final Stats")               # the operator creates it
    b.run(SceneController.VALIDATE_S + 1.0)
    assert b.state["obs_missing_scenes"] == []


def test_controller_when_obs_is_down_then_up():
    obs = FakeObs(SCENES.values(), up=False)
    b = Bench(obs)
    b.run(20.0)
    assert b.state["obs_available"] is False
    assert sum("not reachable" in line for line in b.lines) == 1, "log the outage once"
    obs.up = True
    b.run(SceneController.RECONNECT_S + 1.0)
    assert b.state["obs_available"] is True and b.state["obs_scene"] == COURT


def test_controller_sees_a_scene_changed_by_hand_in_obs():
    obs = FakeObs(SCENES.values())
    b = Bench(obs)
    b.play(1)
    b.end(1)
    b.run(1.0)
    b.play(2)
    b.end(2)
    b.run(4.0)
    assert b.state["obs_scene"] == STATS_SCENE and b.state["scene_prompt"]
    obs.scene = BOX                                # operator clicks in OBS
    b.run(SceneController.POLL_S + 1.0)
    assert b.state["obs_scene"] == BOX and b.state["scene_prompt"] is None


def test_dry_run_shows_decisions_without_touching_obs():
    obs = DryObs(SCENES.values(), start=COURT)
    b = Bench(obs, live=False)
    b.play(1)
    b.end(1)
    b.run(1.0)
    b.play(2)
    b.end(2)
    b.run(4.0)
    assert b.state["obs_enabled"] is False and b.state["obs_available"] is False
    assert b.state["scene_prompt"] == MSG_HALFTIME.format(next=3)
    assert b.log_has("(dry run)") and obs.current_scene() == STATS_SCENE


def test_simulator_period_end_drives_the_whole_flow():
    from parser import parse
    from simulator import game_sequence

    d = SceneDirector(SCENES, stats_after={1}, stats_delay=DELAY)
    timeline, now = [], 0.0
    for _ in range(2):                             # two passes of the simulated period
        for frame, _, pause in game_sequence():
            p = parse(frame)
            timeline.append((now, p))
            now += pause

    on_air, switches, i, cur, t = COURT, [], 0, None, 0.0
    while t <= now + 5:
        while i < len(timeline) and timeline[i][0] <= t:
            cur = timeline[i][1]
            i += 1
        if cur is not None:
            snap = Snapshot(
                now=t, period=cur["period"], minutes=cur["clock_min"],
                seconds=cur["clock_sec"], tenths=cur["clock_tenths"],
                counters=(cur["home_score"], cur["guest_score"], cur["home_fouls"],
                          cur["away_fouls"], cur["home_timeouts"], cur["guest_timeouts"]),
                on_air=on_air)
            actions, _ = d.update(snap)
            for a in actions:
                switches.append(a.scene)
                on_air = a.scene
        t += DT
    assert switches == [STATS_SCENE, COURT], switches


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}\n        {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
