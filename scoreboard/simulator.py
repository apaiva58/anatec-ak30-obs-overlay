"""
simulator.py
============
Simulates Anatec AK30 serial output for testing the parser
and overlay without a physical scoreboard.

Generates a sequence of frames representing a game scenario:
  - Clock counts down
  - Home scores 2+2
  - Guest scores 2+2
  - Home scores 3
  - Free throw made
  - Timeout home
  - Fouls up to bonus
  - Multi-digit scores (10, 20, 99, 100, 119)
  - Sub-second clock

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
    Yields (frame, label, pause_seconds) tuples simulating a 2-minute game sequence.

    Score progression: 2-0, 2-2, 2-5, 4-5, foul away, 5-5, 5-8, 5-10, 7-10, 9-10
    Clock runs continuously through scoring events — stops only on fouls,
    timeouts and free throws, as in a real game.
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

    def clock_run(from_min, from_sec, to_min, to_sec, step_pause=0.08):
        total_from = from_min * 60 + from_sec
        total_to   = to_min * 60 + to_sec
        for total in range(total_from, total_to - 1, -1):
            m = total // 60
            sec = total % 60
            yield state(f"Clock {m}:{sec:02d}", pause=step_pause,
                        clock_min=m, clock_sec=sec, clock_tenths=None, clock_running=True)

    # Baseline
    yield from hold("Baseline", 1, clock_running=False, clock_min=2, clock_sec=0)

    # Clock starts — 2:00 to 1:45, home scores 2 while clock runs
    yield state("Clock starts", clock_running=True)
    yield from clock_run(2, 0, 1, 46)
    yield state("Home +2 (2:0)", home_score=2, clock_min=1, clock_sec=45, pause=0.08)
    yield from clock_run(1, 45, 1, 31)

    # Guest scores 2 while clock runs — 2:2
    yield state("Guest +2 (2:2)", guest_score=2, clock_min=1, clock_sec=30, pause=0.08)
    yield from clock_run(1, 30, 1, 16)

    # Guest scores 3 while clock runs — 2:5
    yield state("Guest +3 (2:5)", guest_score=5, clock_min=1, clock_sec=15, pause=0.08)
    yield from clock_run(1, 15, 1, 6)

    # Home scores 2 while clock runs — 4:5
    yield state("Home +2 (4:5)", home_score=4, clock_min=1, clock_sec=5, pause=0.08)
    yield from clock_run(1, 5, 0, 56)

    # Away foul — clock stops
    yield from hold("Away foul (1)", 1.5, clock_running=False,
                    clock_min=0, clock_sec=55, away_fouls=1)

    # Free throw — clock stopped
    yield from hold("Home free throw (5:5)", 1.5, home_score=5)

    # Clock resumes — 0:55 to 0:36
    yield state("Clock resumes", clock_running=True)
    yield from clock_run(0, 55, 0, 36)

    # Guest scores 3 while clock runs — 5:8
    yield state("Guest +3 (5:8)", guest_score=8, clock_min=0, clock_sec=35, pause=0.08)
    yield from clock_run(0, 35, 0, 26)

    # Guest scores 2 while clock runs — 5:10
    yield state("Guest +2 (5:10)", guest_score=10, clock_min=0, clock_sec=25, pause=0.08)

    # Home timeout — clock stops
    yield from hold("Home timeout", 3, clock_running=False,
                    clock_min=0, clock_sec=25,
                    timeout_active="home", home_timeouts=1)
    yield from hold("Timeout ends", 0.5, timeout_active=None)

    # Clock resumes — 0:25 to 0:16
    yield state("Clock resumes", clock_running=True)
    yield from clock_run(0, 25, 0, 16)

    # Home scores 2 while clock runs — 7:10
    yield state("Home +2 (7:10)", home_score=7, clock_min=0, clock_sec=15, pause=0.08)
    yield from clock_run(0, 15, 0, 6)

    # Home scores 2 while clock runs — 9:10
    yield state("Home +2 (9:10)", home_score=9, clock_min=0, clock_sec=5, pause=0.08)
    yield from clock_run(0, 5, 0, 1)

    # Sub-second countdown. Ends the way the real console does (capture
    # 2026-04-23): the last tenths frame is 0:00.1, then the display drops to
    # plain 0:00 in minute mode. It never shows 0:00.0 at the buzzer.
    for sec in range(4, -1, -1):
        for tenth in range(9, -1, -1):
            if sec == 0 and tenth == 0:
                break
            yield state(f"Clock 0:{sec:02d}.{tenth}",
                       clock_sec=sec, clock_tenths=tenth,
                       clock_running=False, pause=0.08)

    # Buzzer: minute mode (tenths absent), buzzer flag on
    yield from hold("Buzzer", 2, clock_sec=0, clock_tenths=None,
                    service_dot=True)
    yield from hold("End of period", 1, service_dot=False,
                    clock_running=False)
    # Hold at 0:00 for 30 seconds — gives OBS scene switcher time to detect
    yield from hold("Hold 0:00", 30, clock_sec=0, clock_tenths=None,
                    service_dot=False, clock_running=False)


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