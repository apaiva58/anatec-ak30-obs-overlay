"""
reader.py
=========
Reads Anatec AK30 serial frames (23 bytes on wire; 21 data bytes) from the serial port
and updates match_state continuously.

Can run in three modes:
  - serial:   reads from a given USB port, reconnects to that port on loss
  - auto:     discovers the port by probing, rediscovers on loss
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

try:
    import serial
    from serial.tools import list_ports
except ImportError:          # surfaced in start_reader with an install hint
    serial = None
    list_ports = None


FRAME_LENGTH = 21

# Bytes the AK30 actually emits: BEL (service dot), space, ASCII digits.
# Derived from 1,196 captured 21-byte frames across three sessions
# (2026-04-23, -25, -29). Nothing else has ever appeared.
_AK30_BYTES = frozenset([0x07, 0x20] + list(range(0x30, 0x3A)))

# No frames for this long means the link is dead, whatever the OS thinks.
# The console streams continuously at ~11 frames/sec.
_SILENCE_LIMIT_S = 10

# Last port that produced valid frames — tried first on the next discovery.
_LAST_PORT_FILE = os.path.join(os.path.dirname(__file__), ".last_port")

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
    match_state["anatec_clock_tenths"]  = parsed["clock_tenths"]   # None at 1:00 and above
    match_state["anatec_clock"]         = format_clock(parsed)
    match_state["anatec_clock_running"] = clock_running
    match_state["anatec_service_dot"]   = parsed["service_dot"]
    match_state["anatec_connected"]     = True
    match_state["anatec_last_frame_ts"] = time.time()

    # timeout active — service dot on + count increased
    if parsed["service_dot"]:
        if new_home_to > prev_home_to:
            match_state["anatec_timeout"] = "home"
        elif new_away_to > prev_away_to:
            match_state["anatec_timeout"] = "away"
        # service dot on but count unchanged — keep existing timeout state
    else:
        match_state["anatec_timeout"] = None


def _read_serial_once(port: str, baud: int = 2400):
    """Open the port and feed frames into match_state until the link fails.

    Returns on any error, including sustained silence. The caller decides
    whether to retry the same port (serial mode) or rediscover (auto mode).
    Uses the carriage-return terminator to stay frame-aligned.
    """
    ser = None
    try:
        print(f"Connecting to Anatec on {port} @ {baud} baud...")
        ser = serial.Serial(port, baud, timeout=2)
        print("Connected.")
        match_state["anatec_connected"] = True

        # discard first partial frame to get aligned
        ser.read_until(b'\r')

        silent_reads = 0
        silent_limit = max(1, _SILENCE_LIMIT_S // 2)   # reads of 2s each

        while True:
            raw = ser.read_until(b'\r')
            if not raw:
                silent_reads += 1
                if silent_reads >= silent_limit:
                    raise TimeoutError(f"no frames for {_SILENCE_LIMIT_S}s")
                continue
            silent_reads = 0

            frame_bytes = raw.rstrip(b'\r').rstrip(b'\n')
            if len(frame_bytes) == FRAME_LENGTH:
                parsed = parse(bytes(frame_bytes))
                if parsed:
                    _update_state(parsed)

    except Exception as e:
        print(f"Serial error: {e}")
        match_state["anatec_connected"] = False
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


def _read_serial(port: str, baud: int = 2400):
    """Fixed-port reader: reconnects to the same port after any loss."""
    while True:
        _read_serial_once(port, baud)
        print("Retrying in 5 seconds...")
        time.sleep(5)


# ── Port discovery (auto mode) ───────────────────────────────────────────────

def _is_ak30_frame(frame: bytes) -> bool:
    """True if this looks like a frame the AK30 would emit.

    parse() only checks length, so the byte-set check does the real
    discrimination: any other device producing 21-byte lines of nothing
    but digits, spaces and BEL is not a realistic false positive.
    """
    return (len(frame) == FRAME_LENGTH
            and all(b in _AK30_BYTES for b in frame)
            and parse(frame) is not None)


def _candidate_ports() -> list:
    """Serial devices worth probing, in a stable order.

    On macOS prefers /dev/cu.* over /dev/tty.* — the tty. node can block
    on open waiting for carrier detect, which is fatal when probing several
    ports in sequence. Skips Bluetooth and debug consoles.
    """
    found = []
    for info in list_ports.comports():
        dev = info.device
        low = dev.lower()
        if "bluetooth" in low or "debug" in low:
            continue
        if dev.startswith("/dev/tty."):
            cu = "/dev/cu." + dev[len("/dev/tty."):]
            if os.path.exists(cu):
                dev = cu
        if dev not in found:
            found.append(dev)
    return found


def _probe_port(device: str, baud: int, probe_secs: float = 1.5, need: int = 3) -> bool:
    """Open a port briefly and look for consecutive valid AK30 frames.

    At ~11 frames/sec a 1.5s window yields ~16 frames, so three in a row
    is both quick and decisive. A single bad frame resets the count.
    """
    try:
        with serial.Serial(device, baud, timeout=0.5) as ser:
            ser.read_until(b'\r')            # discard partial first frame
            deadline = time.time() + probe_secs
            good = 0
            while time.time() < deadline:
                raw = ser.read_until(b'\r')
                if not raw:
                    continue
                frame = raw.rstrip(b'\r').rstrip(b'\n')
                if _is_ak30_frame(bytes(frame)):
                    good += 1
                    if good >= need:
                        return True
                else:
                    good = 0
    except Exception:
        pass
    return False


def _load_last_port():
    try:
        with open(_LAST_PORT_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def _save_last_port(port: str):
    try:
        with open(_LAST_PORT_FILE, "w") as f:
            f.write(port)
    except OSError:
        pass


def discover_port(baud: int = 2400):
    """Find the port the AK30 is on. Tries the last known port first.

    Returns the device path, or None if no port produced valid frames.
    """
    candidates = _candidate_ports()
    last = _load_last_port()
    if last and last in candidates:
        candidates.remove(last)
        candidates.insert(0, last)

    if not candidates:
        print("[Anatec] No serial devices present.")
        return None

    for dev in candidates:
        print(f"[Anatec] Probing {dev}...")
        if _probe_port(dev, baud):
            return dev
    return None


def _auto_serial(baud: int = 2400):
    """Discover, read, and rediscover on loss. Runs for the process lifetime.

    Rediscovery rather than reconnection matters because the macOS device
    name encodes the USB socket: replugging into a different port changes
    the path, and a fixed-port retry would wait on a name that no longer
    exists.
    """
    while True:
        port = discover_port(baud)
        if port is None:
            match_state["anatec_port"] = None
            match_state["anatec_connected"] = False
            print("[Anatec] Not found — retrying in 5s. Check the USB cable.")
            time.sleep(5)
            continue

        match_state["anatec_port"] = port
        _save_last_port(port)
        print(f"[Anatec] Found on {port}")
        _read_serial_once(port, baud)       # returns only on loss
        match_state["anatec_port"] = None
        print("[Anatec] Connection lost — rediscovering...")


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

    mode: "serial", "auto" or "simulate"
    port: serial port path (required for serial mode, ignored otherwise)
    """
    match_state["anatec_mode"] = mode
    match_state["anatec_port"] = port if mode == "serial" else None

    if mode in ("serial", "auto") and serial is None:
        print("pyserial not installed — run: pip3 install pyserial --break-system-packages")
        match_state["anatec_mode"] = "off"
        return

    if mode == "serial":
        if not port:
            print("Serial mode requires a port argument.")
            match_state["anatec_mode"] = "off"
            return
        t = threading.Thread(target=_read_serial, args=(port, baud), daemon=True)
    elif mode == "auto":
        t = threading.Thread(target=_auto_serial, args=(baud,), daemon=True)
    else:
        t = threading.Thread(target=_read_simulate, daemon=True)

    t.start()
    return t
