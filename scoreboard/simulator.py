"""
simulator.py
============
Simulates Anatec AK30 serial output for testing the parser
and overlay without a physical scoreboard.

Generates a whole match of four short quarters (2:00 each on the console,
about 20 s of wall time per quarter):
  - each quarter: baskets while the clock runs, a foul and free throw with
    the clock stopped, a timeout, a sub-second countdown, the buzzer
  - quarter scores follow QUARTERS, which mirrors mock_data.json
  - scores carry over; team fouls reset each quarter, timeouts at halftime
  - a short break between Q1-Q2 and Q3-Q4, a 30 s halftime after Q2
  - after Q4, a few seconds of "desk finalising", then FINAL_LABEL; in mock
    mode the reader turns the match Final there, so the final scene shows
  - one pass takes about 2.8 minutes; the reader loops it, and each loop
    returns from period 4 to 1, which scene control treats as a new game

Byte positions (confirmed 2026-04-23):
  16+17+18  home score (hundreds, tens, units)
  12+11+10  guest score (hundreds, tens, units)
  2+3       home fouls (tens, units)
  4+5       away fouls (tens, units)
  6         period
  7         timeout flag (T=home, G=guest, space=none)
  8         guest timeouts
  9         home timeouts
  13+14     clock seconds (or space+tenths below 1 min)
  15        service dot (0x07=ON)
  19+20     clock minutes (or seconds below 1 min)

Usage:
    python3 scoreboard/simulator.py
"""

import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from parser import parse, format_clock

# The AK30 transmits continuously at roughly 11 frames/sec (2400 baud 8N1,
# 22 bytes on the wire per frame). A stopped clock is still a stream of
# identical frames, not silence — hold() below reproduces that.
FRAME_PERIOD = 0.09

# Breaks, in wall-clock seconds. Real breaks are minutes long; these are
# shortened for testing. Scene control ignores console counters for 30 s
# after a buzzer, so with HALFTIME_S = 30 the return to the court comes on
# the first basket of Q3, about 5 s after that window closes.
BREAK_S = 5
HALFTIME_S = 30
DESK_S = 5           # Q4 buzzer to "Final" in FOYS; minutes in a real match
FINAL_HOLD_S = 25    # time to look at the final scene before the next pass

# The reader matches this label to turn a mock match Final (reader.py).
FINAL_LABEL = "Match final"

# Points per quarter (home, guest). These are the quarters in
# mock_data.json, so with --mock the console ends where mock FOYS says the
# match ended (78-71) and the final slate agrees with the bar.
# tests/test_scene_logic.py checks the two stay equal.
QUARTERS = [(20, 18), (18, 15), (22, 19), (18, 19)]


def make_frame(
    home_score=0,
    guest_score=0,
    home_fouls=0,
    away_fouls=0,
    period=1,
    clock_min=10,
    clock_sec=0,
    clock_tenths=None,
    clock_running=False,
    timeout_active=None,
    home_timeouts=0,
    guest_timeouts=0,
    service_dot=False,
) -> bytes:
    """Build a 21-byte Anatec frame from game state."""

    def a(n):
        """ASCII encode a single digit (0-9)."""
        return 0x30 + max(0, min(9, n))

    def d(n, pos):
        """Extract digit at decimal position (0=units, 1=tens, 2=hundreds)."""
        return (n // (10 ** pos)) % 10

    f = bytearray(21)

    # pos 0+1 — always 0x30 0x30
    f[0] = 0x30
    f[1] = 0x30

    # pos 2+3 — home fouls (tens, units)
    f[2] = a(d(home_fouls, 1)) if home_fouls >= 10 else 0x20
    f[3] = a(d(home_fouls, 0))

    # pos 4+5 — away fouls (tens, units)
    f[4] = a(d(away_fouls, 1)) if away_fouls >= 10 else 0x20
    f[5] = a(d(away_fouls, 0))

    # pos 6 — period
    f[6] = a(period)

    # pos 7 — timeout flag
    f[7] = 0x54 if timeout_active == "home" else (0x47 if timeout_active == "guest" else 0x20)

    # pos 8+9 — guest/home timeout counts
    f[8] = a(guest_timeouts)
    f[9] = a(home_timeouts)

    # pos 10+11+12 — guest score (units, tens, hundreds)
    f[10] = a(d(guest_score, 0))
    f[11] = a(d(guest_score, 1)) if guest_score >= 10 else 0x20
    f[12] = a(d(guest_score, 2)) if guest_score >= 100 else 0x20

    # pos 13+14 — clock seconds / tenths
    # pos 15 — service dot
    # pos 19+20 — clock minutes / seconds (sub-second mode)

    if clock_tenths is not None:
        # sub-second mode: pos 13=space, pos 14=tenths, pos 19+20=seconds
        f[13] = 0x20
        f[14] = a(clock_tenths)
        f[15] = 0x07 if service_dot else 0x20
        f[16] = 0x20
        f[17] = 0x20
        f[18] = a(d(home_score, 0))
        f[19] = a(d(clock_sec, 1)) if clock_sec >= 10 else 0x20
        f[20] = a(d(clock_sec, 0))
    else:
        # normal mode
        # pos 13 = seconds units, pos 14 = seconds tens (confirmed session 3)
        f[13] = a(clock_sec % 10)
        f[14] = a(clock_sec // 10)
        f[15] = 0x07 if service_dot else 0x20
        f[16] = a(d(home_score, 2)) if home_score >= 100 else 0x20
        f[17] = a(d(home_score, 1)) if home_score >= 10 else 0x20
        f[18] = a(d(home_score, 0))

        # running detection is done by reader via consecutive frame comparison
        # no explicit running flag — encode minutes as tens+units always
        f[19] = a(clock_min // 10) if clock_min >= 10 else 0x20
        f[20] = a(clock_min % 10)

    return bytes(f)


def game_sequence():
    """
    Yields (frame, label, pause_seconds) tuples simulating a whole match.

    Per quarter the points in QUARTERS, as baskets while the clock runs,
    plus an away foul with a home free throw and a home timeout, both with
    the clock stopped, as in a real game.
    """
    s = dict(
        home_score=0, guest_score=0,
        home_fouls=0, away_fouls=0,
        period=1, clock_min=2, clock_sec=0,
        clock_tenths=None, clock_running=False,
        timeout_active=None,
        home_timeouts=0, guest_timeouts=0,
        service_dot=False,
    )

    def state(label, pause=0.5, **kwargs):
        s.update(kwargs)
        return make_frame(**s), label, pause

    def hold(label, seconds, **kwargs):
        """Re-emit the current frame at hardware cadence for `seconds`.

        Used wherever the game pauses. The real console keeps transmitting,
        so the reader keeps seeing fresh frames; sleeping instead would make
        the feed look dead to any freshness check.
        """
        s.update(kwargs)
        frame = make_frame(**s)
        for _ in range(max(1, round(seconds / FRAME_PERIOD))):
            yield frame, label, FRAME_PERIOD

    def quarter(q, home_pts, guest_pts):
        """One quarter in which home scores home_pts and guest guest_pts.

        Home gets one free throw (after the foul at 0:55); everything else
        is split into baskets of 2, plus one 3 when the remainder is odd.
        The baskets alternate home and guest and are spread evenly over the
        running clock, away from the stops at 0:55 and 0:25 and the last
        five seconds.
        """
        def baskets(points):
            out = []
            if points % 2:
                out.append(3)
                points -= 3
            return out + [2] * (points // 2)

        home, guest = baskets(home_pts - 1), baskets(guest_pts)
        events = []
        for i in range(max(len(home), len(guest))):
            if i < len(home):
                events.append(("home", home[i]))
            if i < len(guest):
                events.append(("guest", guest[i]))
        pool = [t for t in range(119, 5, -1) if t not in (55, 25)]
        event_at = {pool[int((k + 0.5) * len(pool) / len(events))]: ev
                    for k, ev in enumerate(events)}

        def tally():
            return f"{s['home_score']}:{s['guest_score']}"

        # Console set for the new quarter: period on, clock at 2:00, team
        # fouls back to zero.
        yield from hold(f"Q{q} ready", 1, period=q, clock_running=False,
                        clock_min=2, clock_sec=0, clock_tenths=None,
                        home_fouls=0, away_fouls=0,
                        timeout_active=None, service_dot=False)
        yield state(f"Q{q} clock starts", clock_running=True)

        # Whole seconds from 1:59 down to 0:05. Baskets land while the clock
        # runs; the clock stops only for the foul and the timeout.
        for total in range(119, 4, -1):
            m, sec = divmod(total, 60)
            label = f"Clock {m}:{sec:02d}"
            if total in event_at:
                team, pts = event_at[total]
                key = "home_score" if team == "home" else "guest_score"
                s[key] += pts
                label = f"Q{q} {team} +{pts} ({tally()})"
            yield state(label, pause=0.08, clock_min=m, clock_sec=sec,
                        clock_tenths=None, clock_running=True)

            if total == 55:
                # Away foul, home free throw: clock stopped
                yield from hold(f"Q{q} away foul", 1.5, clock_running=False,
                                away_fouls=s["away_fouls"] + 1)
                s["home_score"] += 1
                yield from hold(f"Q{q} home free throw ({tally()})", 1.5)
                yield state(f"Q{q} clock resumes", clock_running=True)

            if total == 25:
                # Home timeout: clock stopped
                yield from hold(f"Q{q} home timeout", 3, clock_running=False,
                                timeout_active="home",
                                home_timeouts=s["home_timeouts"] + 1)
                yield from hold(f"Q{q} timeout ends", 0.5, timeout_active=None)
                yield state(f"Q{q} clock resumes", clock_running=True)

        # Sub-second countdown. Ends the way the real console does (capture
        # 2026-04-23): the last tenths frame is 0:00.1, then the display drops
        # to plain 0:00 in minute mode. It never shows 0:00.0 at the buzzer.
        for sec in range(4, -1, -1):
            for tenth in range(9, -1, -1):
                if sec == 0 and tenth == 0:
                    break
                yield state(f"Q{q} clock 0:{sec:02d}.{tenth}",
                            clock_sec=sec, clock_tenths=tenth,
                            clock_running=False, pause=0.08)

        # Buzzer: minute mode (tenths absent), buzzer flag on
        yield from hold(f"Q{q} buzzer", 2, clock_sec=0, clock_tenths=None,
                        service_dot=True)
        yield from hold(f"Q{q} end of period", 1, service_dot=False,
                        clock_running=False)

    # The match. Breaks hold the console at 0:00 of the quarter just ended;
    # the period number only moves when the next quarter is set up.
    (q1, q2, q3, q4) = QUARTERS
    yield from quarter(1, *q1)
    yield from hold("Break Q1-Q2", BREAK_S)
    yield from quarter(2, *q2)
    yield from hold("Halftime", HALFTIME_S, home_timeouts=0, guest_timeouts=0)
    yield from quarter(3, *q3)
    yield from hold("Break Q3-Q4", BREAK_S)
    yield from quarter(4, *q4)
    yield from hold("Desk finalising", DESK_S)
    yield from hold(FINAL_LABEL, FINAL_HOLD_S)


def run():
    print("Anatec AK30 Simulator")
    print("=" * 50)
    print()

    last_label = None
    for frame, label, pause in game_sequence():
        parsed = parse(frame)
        if not parsed:
            print(f"[PARSE ERROR] {label}")
            continue
        if label == last_label:
            # repeated hold frame — stream it, but do not reprint
            time.sleep(pause)
            continue
        last_label = label
        clock = format_clock(parsed)
        print(f"[{clock}] {label}")
        print(f"  Home {parsed['home_score']} — {parsed['guest_score']} Guest"
              f" | Period {parsed['period']}"
              f" | Fouls H:{parsed['home_fouls']} A:{parsed['away_fouls']}"
              f" | TO:{parsed['timeout_active'] or 'none'}"
              f" | dot:{parsed['service_dot']}")
        print(f"  frame: {frame.hex()}")
        print()
        time.sleep(pause)

    print("Done.")


if __name__ == "__main__":
    run()