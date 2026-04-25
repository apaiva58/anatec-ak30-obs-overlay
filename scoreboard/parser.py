"""
parser.py
=========
Parses Anatec AK30 serial frames (23 bytes on wire; 21 data bytes) into a readable dict.

Frame format: ASCII encoded, space-separated values.
All values transmitted as ASCII: '0'=0x30, '1'=0x31, etc.
Spaces (0x20) represent zero or empty at that position.

Byte positions (confirmed from capture sessions 2026-04-20, 2026-04-23, 2026-04-25):

  HOME SCORE
  16      hundreds
  17      tens
  18      units

  GUEST SCORE
  12      hundreds
  11      tens
  10      units

  HOME FOULS
  2       tens (activates at 10)
  3       units

  AWAY FOULS
  4       tens (activates at 10)
  5       units

  PERIOD
  6       period number (1=Q1, 2=Q2, 3=Q3, 4=Q4)

  CLOCK (above 1 minute)
  19      minutes tens (space when minutes < 10)
  20      minutes units
  14      seconds tens
  13      seconds units
  NOTE: pos 13=units, pos 14=tens (confirmed session 3, 2026-04-25)

  CLOCK (below 1 minute — tenths of second mode)
  13      space (0x20) signals tenths mode
  14      tenths of second (counts 9->0 per second)
  19      seconds tens (space when seconds < 10)
  20      seconds units
  NOTE: pos 13=space is the trigger (confirmed session 2, 2026-04-23)

  RUNNING DETECTION
  Above 1 minute: no explicit flag. Running is detected by comparing
  consecutive clock values. At 1 minute, pos 20 = 0x31 = both '1' and
  potentially confused with running. Use consecutive frame comparison.
  Below 1 minute: running is implicit from pos 14 (tenths) changing.

  SERVICE DOT
  15      0x07 = ON (ASCII BEL), 0x20 = OFF
  Activates at 0:00.0 and during timeouts (confirmed session 3)

  TIMEOUT
  7       always 0x20 — no timeout flag here (originally assumed, now corrected)
  8       guest timeouts taken
  9       home timeouts taken
  Timeout detection: service dot (pos 15 = 0x07) + timeout count increase

  UNKNOWN
  0+1     always 0x30 0x30 — likely shot clock (00 when not connected)
"""

FRAME_LENGTH = 21


def _digit(frame: bytes, pos: int) -> int:
    """Read ASCII digit at position. Returns 0 for space or non-digit."""
    v = frame[pos]
    if 0x30 <= v <= 0x39:
        return v - 0x30
    return 0


def _number(frame: bytes, *positions) -> int:
    """Read multi-digit number from multiple positions (hundreds, tens, units)."""
    result = 0
    for pos in positions:
        result = result * 10 + _digit(frame, pos)
    return result


def parse(frame: bytes) -> dict | None:
    """
    Parse a 21-byte Anatec AK30 data frame (CR terminator already stripped).
    Returns a dict or None if frame is invalid.
    """
    if len(frame) != FRAME_LENGTH:
        return None

    # Clock mode detection
    # Sub-second mode: pos 13 = space (0x20)
    # Normal mode:     pos 13 = seconds units digit
    sub_second = frame[13] == 0x20

    if sub_second:
        # Below 1 minute
        # pos 14 = tenths, pos 19 = seconds tens, pos 20 = seconds units
        tenths  = _digit(frame, 14)
        seconds = _number(frame, 19, 20)
        minutes = 0
        clock_running = False  # near end of period, always stopped in display
    else:
        # Above 1 minute
        # pos 14 = seconds tens, pos 13 = seconds units
        tenths  = None
        seconds = _number(frame, 14, 13)

        # Minutes: pos 19 = tens, pos 20 = units
        # No explicit running flag — running cannot be determined from single frame
        # at 1:xx minutes because pos 20 = '1' is ambiguous.
        # Reader detects running by comparing consecutive frames.
        min_tens = _digit(frame, 19) if frame[19] != 0x20 else 0
        min_units = _digit(frame, 20)
        minutes = min_tens * 10 + min_units
        clock_running = False  # set by reader via consecutive frame comparison

    return {
        "home_score":      _number(frame, 16, 17, 18),
        "guest_score":     _number(frame, 12, 11, 10),
        "home_fouls":      _number(frame, 2, 3),
        "away_fouls":      _number(frame, 4, 5),
        "period":          _digit(frame, 6),
        "clock_min":       minutes,
        "clock_sec":       seconds,
        "clock_tenths":    tenths,
        "clock_running":   clock_running,
        "sub_second":      sub_second,
        "home_timeouts":   _digit(frame, 9),
        "guest_timeouts":  _digit(frame, 8),
        "service_dot":     frame[15] == 0x07,
    }


def format_clock(parsed: dict) -> str:
    """Format clock as MM:SS or 0:SS.t string."""
    if parsed["sub_second"]:
        t = parsed["clock_tenths"] if parsed["clock_tenths"] is not None else 0
        return f"0:{parsed['clock_sec']:02d}.{t}"
    return f"{parsed['clock_min']:02d}:{parsed['clock_sec']:02d}"
