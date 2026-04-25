"""
reader.py
=========
Reads 21-byte frames from the Anatec AK30 serial port
and updates match_state continuously.

Can run in two modes:
  - serial: reads from real USB port
  - simulate: uses simulator.py for testing

Timeout detection:
    Service dot (pos 15 = 0x07) + timeout count increase at pos 8/9.
    When service dot goes off, timeout_active is cleared.

Clock running detection:
    No explicit running flag exists in the frame at 1:xx minutes.
    Running is detected by comparing consecutive clock values.
    Below 1 minute, running is implicit from tenths changing.
"""

import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from parser import parse, format_clock
from state import match_state


FRAME_LENGTH = 21

# previous clock for running detection
_prev_clock = (None, None)


def _update_state(parsed: dict):
    """Update match_state from a parsed Anatec frame."""
    global _prev_clock

    if not parsed:
        return

    # detect clock running by comparing consecutive frames
    new_clock = (parsed["clock_min"], parsed["clock_sec"])
    clock_running = (new_clock != _prev_clock) if _prev_clock != (None, None) else False
    _prev_clock = new_clock

    # read previous timeout counts before updating
    prev_home_to = match_state.get("anatec_home_timeouts", 0)
    prev_away_to = match_state.get("anatec_guest_timeouts", 0)

    new_home_to = parsed["home_timeouts"]
    new_away_to = parsed["guest_timeouts"]

    match_state["anatec_home_score"]    = parsed["home_score"]
    match_state["anatec_guest_score"]   = parsed["guest_score"]
    match_state["anatec_home_fouls"]    = parsed["home_fouls"]
    match_state["anatec_guest_fouls"]   = parsed["away_fouls"]
    match_state["anatec_home_timeouts"] = new_home_to
    match_state["anatec_guest_timeouts"]= new_away_to
    match_state["anatec_period"]        = parsed["period"]
    match_state["anatec_clock_min"]     = parsed["clock_min"]
    match_state["anatec_clock_sec"]     = parsed["clock_sec"]
    match_state["anatec_clock"]         = format_clock(parsed)
    match_state["anatec_clock_running"] = clock_running
    match_state["anatec_service_dot"]   = parsed["service_dot"]
    match_state["anatec_connected"]     = True

    # timeout active — service dot on + count increased
    if parsed["service_dot"]:
        if new_home_to > prev_home_to:
            match_state["anatec_timeout"] = "home"
        elif new_away_to > prev_away_to:
            match_state["anatec_timeout"] = "away"
        # service dot on but count unchanged — keep existing timeout state
    else:
        match_state["anatec_timeout"] = None


def _read_serial(port: str, baud: int = 2400):
    """Read frames from real serial port with auto-reconnect.

    Uses carriage return terminator to stay frame-aligned.
    """
    try:
        import serial
    except ImportError:
        print("pyserial not installed — run: pip3 install pyserial --break-system-packages")
        return

    while True:
        print(f"Connecting to Anatec on {port} @ {baud} baud...")
        try:
            ser = serial.Serial(port, baud, timeout=2)
            print("Connected.")
            match_state["anatec_connected"] = True

            # discard first partial frame to get aligned
            ser.read_until(b'\r')

            while True:
                raw = ser.read_until(b'\r')
                if not raw:
                    continue
                frame_bytes = raw.rstrip(b'\r').rstrip(b'\n')
                if len(frame_bytes) == FRAME_LENGTH:
                    parsed = parse(bytes(frame_bytes))
                    if parsed:
                        _update_state(parsed)

        except Exception as e:
            print(f"Serial error: {e} — retrying in 5 seconds")
            match_state["anatec_connected"] = False
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(5)


def _read_simulate():
    """Feed frames from simulator."""
    from simulator import game_sequence, make_frame
    print("Anatec reader running in SIMULATE mode.")
    match_state["anatec_connected"] = True

    while True:
        for frame, label, pause in game_sequence():
            parsed = parse(frame)
            if parsed:
                _update_state(parsed)
                # print(f"[SIM] {label} — {match_state['anatec_clock']}")
            time.sleep(pause)
        time.sleep(2)


def start_reader(mode: str = "simulate", port: str = None, baud: int = 2400):
    """
    Start the Anatec reader in a background thread.

    mode: "serial" or "simulate"
    port: serial port path (required for serial mode)
    """
    if mode == "serial":
        if not port:
            print("Serial mode requires a port argument.")
            return
        t = threading.Thread(target=_read_serial, args=(port, baud), daemon=True)
    else:
        t = threading.Thread(target=_read_simulate, daemon=True)

    t.start()
    return t
