"""
parser.py
=========
Parses 21-byte Anatec AK30 serial frames into a readable dict.

Frame format: ASCII encoded, space-separated digits.
All values transmitted as ASCII: '0'=0x30, '1'=0x31, etc.
Spaces (0x20) are separators or represent zero/empty.

Byte positions:
  3       — home team fouls
  5+6     — guest fouls (ambiguous with period — see protocol.md)
  7       — timeout active flag (T=home, G=guest, space=none)
  8       — guest timeout count
  9       — home timeout count
  10      — guest score (units)
  13      — clock seconds tens
  14      — clock seconds units
  15      — shot clock / service dot (0x07=on)
  18      — home score (units)
  19      — clock minutes tens
  20      — clock minutes units
"""

FRAME_LENGTH = 21


def _digit(frame: bytes, pos: int) -> int:
    v = frame[pos]
    if 0x30 <= v <= 0x39:
        return v - 0x30
    return 0


def parse(frame: bytes) -> dict | None:
    """
    Parse a 21-byte Anatec AK30 frame.
    Returns a dict or None if frame is invalid.
    """
    if len(frame) != FRAME_LENGTH:
        return None

    # Clock
    min_tens = _digit(frame, 19) if frame[19] != 0x20 else 0
    min_units = _digit(frame, 20)
    sec_tens = _digit(frame, 13)
    sec_units = _digit(frame, 14)

    minutes = min_tens * 10 + min_units
    seconds = sec_tens * 10 + sec_units

    # Detect clock running — pos 20 = 0x31
    clock_running = frame[20] == 0x31 and frame[19] == 0x20

# When running: pos 19 = full minutes, pos 20 = running flag
# When stopped: pos 19 = tens, pos 20 = units
    if frame[20] == 0x31:
        minutes = _digit(frame, 19)
        clock_running = True
    else:
        min_tens = _digit(frame, 19) if frame[19] != 0x20 else 0
        min_units = _digit(frame, 20)
        minutes = min_tens * 10 + min_units
        clock_running = False

    # Timeout
    timeout_flag = frame[7]
    if timeout_flag == 0x54:
        timeout_active = "home"
    elif timeout_flag == 0x47:
        timeout_active = "guest"
    else:
        timeout_active = None

    return {
        "home_score":      _digit(frame, 18),
        "guest_score":     _digit(frame, 10),
        "home_fouls":      _digit(frame, 3),
        "guest_fouls":     _digit(frame, 6),   # units only — see protocol.md
        "period":          _digit(frame, 6),   # ambiguous with guest fouls
        "clock_min":       minutes,
        "clock_sec":       seconds,
        "clock_running":   clock_running,
        "timeout_active":  timeout_active,
        "home_timeouts":   _digit(frame, 9),
        "guest_timeouts":  _digit(frame, 8),
        "service_dot":     frame[15] == 0x07,
    }


def format_clock(parsed: dict) -> str:
    """Format clock as MM:SS string."""
    return f"{parsed['clock_min']:02d}:{parsed['clock_sec']:02d}"