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
  - Fouls

Usage:
    python scoreboard/simulator.py

    Or import and use generate_frames() in tests.
"""

import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from parser import parse, format_clock


def make_frame(
    home_score=0,
    guest_score=0,
    home_fouls=0,
    guest_fouls=0,
    period=1,
    clock_min=10,
    clock_sec=0,
    clock_running=False,
    timeout_active=None,
    home_timeouts=0,
    guest_timeouts=0,
    service_dot=False,
) -> bytes:
    """Build a 21-byte Anatec frame from game state."""

    def a(n):
        """ASCII encode a single digit."""
        return 0x30 + max(0, min(9, n))

    f = bytearray(21)

    f[0]  = 0x30
    f[1]  = 0x30
    f[2]  = 0x20
    f[3]  = a(home_fouls)
    f[4]  = 0x20
    f[5]  = a(guest_fouls // 10) if guest_fouls >= 10 else 0x30
    # pos 6 — period when no guest fouls, guest foul units when fouled
    # NOTE: ambiguous — needs second capture session to verify
    f[6]  = a(guest_fouls % 10) if guest_fouls > 0 else a(period)
    f[7]  = 0x54 if timeout_active == "home" else (0x47 if timeout_active == "guest" else 0x20)
    f[8]  = a(guest_timeouts)
    f[9]  = a(home_timeouts)
    f[10] = a(guest_score)
    f[11] = 0x20
    f[12] = 0x20
    f[13] = a(clock_sec // 10)
    f[14] = a(clock_sec % 10)
    f[15] = 0x07 if service_dot else 0x20
    f[16] = 0x20
    f[17] = 0x20
    f[18] = a(home_score)
    # pos 19+20 — clock minutes
    # when running: pos 20 = 0x31 (running flag), pos 19 = full minutes
    # when stopped: pos 19 = tens, pos 20 = units
    # NOTE: ambiguous at 1:xx when running — needs verification
    if clock_running:
        f[19] = a(clock_min)
        f[20] = 0x31
    else:
        f[19] = a(clock_min // 10) if clock_min >= 10 else 0x20
        f[20] = a(clock_min % 10)

    return bytes(f)


def game_sequence():
    """
    Yields (frame, label, pause_seconds) tuples simulating a game.
    """
    s = dict(
        home_score=0, guest_score=0,
        home_fouls=0, guest_fouls=0,
        period=1, clock_min=10, clock_sec=0,
        clock_running=False, timeout_active=None,
        home_timeouts=0, guest_timeouts=0,
        service_dot=False,
    )

    def state(label, pause=1.0, **kwargs):
        s.update(kwargs)
        return make_frame(**s), label, pause

    yield state("Baseline — all zero, clock stopped", pause=2)

    # Clock counts down from 10:00
    yield state("Clock starts", clock_running=True, clock_min=10, clock_sec=0)
    for sec in range(59, 29, -1):
        yield state(f"Clock 9:{sec:02d}", clock_min=9, clock_sec=sec, pause=0.1)

    # Home scores 2
    yield state("Home +2 (score 2:0)", clock_running=False,
                clock_min=9, clock_sec=30, home_score=2, pause=2)

    # Clock runs again
    yield state("Clock resumes", clock_running=True)
    for sec in range(29, 9, -1):
        yield state(f"Clock 9:{sec:02d}", clock_min=9, clock_sec=sec, pause=0.1)

    # Home scores 2 again
    yield state("Home +2 (score 4:0)", clock_running=False,
                clock_min=9, clock_sec=10, home_score=4, pause=2)

    # Guest scores 2
    yield state("Guest +2 (score 4:2)", guest_score=2, pause=2)

    # Guest scores 2
    yield state("Guest +2 (score 4:4)", guest_score=4, pause=2)

    # Clock runs
    yield state("Clock resumes", clock_running=True, clock_min=9, clock_sec=10)
    for sec in range(9, 0, -1):
        yield state(f"Clock 9:0{sec}", clock_min=9, clock_sec=sec, pause=0.1)

    # Home scores 3
    yield state("Home +3 (score 7:4)", clock_running=False,
                clock_min=9, clock_sec=0, home_score=7, pause=2)

    # Free throw made
    yield state("Home free throw (score 8:4)", home_score=8, pause=2)

    # Home timeout
    yield state("Home timeout", timeout_active="home",
                home_timeouts=1, pause=3)
    yield state("Timeout ends", timeout_active=None, pause=1)

    # Fouls
    yield state("Home foul (1)", home_fouls=1, pause=2)
    yield state("Guest foul (1)", guest_fouls=1, pause=2)
    yield state("Home foul (2)", home_fouls=2, pause=2)
    yield state("Home foul (3)", home_fouls=3, pause=2)
    yield state("Home foul (4) — BONUS", home_fouls=4, pause=2)

    # Period 2
    yield state("Period 2", period=2, clock_min=10, clock_sec=0,
                home_fouls=0, guest_fouls=0, clock_running=False, pause=2)

    yield state("End of simulation", pause=1)


def run():
    print("Anatec AK30 Simulator")
    print("=" * 50)
    print()

    for frame, label, pause in game_sequence():
        parsed = parse(frame)
        clock = format_clock(parsed)
        print(f"[{clock}] {label}")
        print(f"  Home {parsed['home_score']} — {parsed['guest_score']} Guest"
              f" | Period {parsed['period']}"
              f" | Fouls H:{parsed['home_fouls']} G:{parsed['guest_fouls']}"
              f" | TO:{parsed['timeout_active'] or 'none'}")
        print(f"  frame: {frame.hex()}")
        print()
        time.sleep(pause)

    print("Done.")


if __name__ == "__main__":
    run()