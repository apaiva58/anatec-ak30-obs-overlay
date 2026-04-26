# Anatec AK30 Serial Protocol

Reverse-engineered from the Anatec AK30-IPF controller via four capture
sessions at Almere Pioneers Basketball, Topsportcentrum Almere.

Session 1: 2026-04-20
Session 2: 2026-04-23
Session 3: 2026-04-25 (clock positions corrected, timeout corrected)
Session 4: 2026-04-25 (possession indicator confirmed at pos 7)
Session 5: 2026-04-26 (signal/buzzer button confirmed at pos 15)

---

## Connection

  Interface:  USB-B (device side)
  Baud rate:  2400
  Format:     8N1
  Port:       /dev/tty.usbserial-XXXX (macOS)

Find the port:

    ls /dev/tty.*

Run the capture tool:

    python3 capture.py --port /dev/tty.usbserial-XXXX

---

## Frame Format

  Length:    21 bytes
  Encoding:  ASCII
  Terminator: carriage return (0x0D)
  Content:   display buffer — the frame reflects exactly what is shown
             on the physical scoreboard display

The controller transmits continuously regardless of whether anything
is connected to the USB port.

All digit values are ASCII encoded:
  '0' = 0x30
  '1' = 0x31
  ...
  '9' = 0x39
  ' ' = 0x20  (space — empty or zero at that position)

CRITICAL: Read until carriage return to stay frame-aligned.
Do not slice the byte stream into fixed 21-byte chunks without
first finding a frame boundary. See capture.py for reference.

---

## Byte Positions (all confirmed)

### Scores

  Pos  Field                 Notes
  ---  -------------------   -----------------------------------------
  16   Home score hundreds   space (0x20) when score < 100
  17   Home score tens       space (0x20) when score < 10
  18   Home score units      always present

  12   Guest score hundreds  space (0x20) when score < 100
  11   Guest score tens      space (0x20) when score < 10
  10   Guest score units     always present

Score calculation:

  home_score  = (pos16 * 100) + (pos17 * 10) + pos18
  guest_score = (pos12 * 100) + (pos11 * 10) + pos10

### Fouls

  Pos  Field               Notes
  ---  -----------------   -----------------------------------------
  2    Home fouls tens     space (0x20) when fouls < 10
  3    Home fouls units    always present

  4    Away fouls tens     space (0x20) when fouls < 10
  5    Away fouls units    always present

Home and away fouls are fully independent positions.
There is no ambiguity with the period number (resolved session 2).

### Period

  Pos  Field               Notes
  ---  -----------------   -----------------------------------------
  6    Period number       1=Q1, 2=Q2, 3=Q3, 4=Q4, 5=OT

Maximum period on Anatec AK30 is 5 (one overtime period).
The controller does not support OT2 or beyond.

### Possession Indicator

  Pos  Field               Notes
  ---  -----------------   -----------------------------------------
  7    Possession          0x54 ('T') = home team (Thuis)
                           0x47 ('G') = guest team (Gasten)
                           0x20       = neutral / no possession

Signals which team has possession or service — the jump ball arrow.
Confirmed session 4 (2026-04-25) via serve home / serve away / serve out
button sequence.

NOTE: This was originally assumed to be a timeout flag. That was incorrect.
Timeout is NOT signaled at pos 7.

### Timeouts

  Pos  Field               Notes
  ---  -----------------   -----------------------------------------
  7    Possession indicator  NOT a timeout flag (see above)
  8    Guest timeouts taken  count increments when timeout taken
  9    Home timeouts taken   count increments when timeout taken

Timeout detection (confirmed session 3, 2026-04-25):
  The Anatec does NOT transmit a timeout active flag at pos 7.
  Timeout is detected by combining two signals:
  1. Buzzer (pos 15 = 0x07) activates
  2. Home or away timeout count (pos 9 or pos 8) increases

  Which team called the timeout is determined by which count increased.
  When the buzzer goes off (pos 15 = 0x20), the timeout has ended.

Timeout counts per half (NBB basketball):
  Q1+Q2 (first half):   max 2 per team
  Q3+Q4 (second half):  max 3 per team
  Overtime:             max 1 per team

Counts reset when the operator presses the reset button.

### Clock (above 1 minute)

  Pos  Field               Notes
  ---  -----------------   -----------------------------------------
  19   Minutes tens        space (0x20) when minutes < 10
  20   Minutes units
  14   Seconds tens
  13   Seconds units

NOTE: pos 13 = units, pos 14 = tens. Confirmed session 3 (2026-04-25).
Earlier documentation had these reversed.

Running detection:
  There is no explicit clock running flag in the frame.
  Running is detected by comparing consecutive frames — if the clock
  value changes between frames, the clock is running.
  At 1:xx minutes pos 20 = 0x31 which is also the digit '1' —
  there is no way to distinguish stopped from running in a single frame.

Examples (all stopped):

  Clock 6:02:
    pos 19 = 0x20 (space — minutes < 10)
    pos 20 = 0x36 (6 — minutes units)
    pos 14 = 0x30 (0 — seconds tens)
    pos 13 = 0x32 (2 — seconds units)
    result: 6:02

  Clock 5:53:
    pos 19 = 0x20 (space)
    pos 20 = 0x35 (5)
    pos 14 = 0x35 (5 — seconds tens)
    pos 13 = 0x33 (3 — seconds units)
    result: 5:53

### Clock (below 1 minute — tenths of second mode)

When the clock drops below 1 minute the display switches to showing
seconds and tenths of a second.

Detection: pos 13 = 0x20 (space) signals tenths mode is active.
NOTE: pos 13, not pos 14. Confirmed sessions 2 and 3.

  Pos  Field               Notes
  ---  -----------------   -----------------------------------------
  13   0x20 (space)        tenths mode active
  14   Tenths of second    counts 9 to 0 per second
  19   Seconds tens        space (0x20) when seconds < 10
  20   Seconds units

Running detection below 1 minute:
  No explicit flag. Running is implicit — pos 14 (tenths) cycles
  9->8->7...->0->9 and pos 20 (seconds) decrements each full cycle.

Example (clock 0:04.7):

  pos 13 = 0x20 (space — tenths mode)
  pos 14 = 0x37 (7 — tenths)
  pos 19 = 0x20 (space — seconds < 10)
  pos 20 = 0x34 (4 — seconds units)
  result: 0:04.7

### Buzzer

  Pos  Field               Notes
  ---  -----------------   -----------------------------------------
  15   Buzzer              0x07 = ON (ASCII BEL drives physical buzzer)
                           0x20 = OFF

The buzzer activates for three distinct events. Distinguish them by
checking pos 8/9 (timeout counts):

  Event            pos 15   pos 8/9
  ---------------  -------  ---------------------------
  Timeout home     0x07     pos 9 increments
  Timeout away     0x07     pos 8 increments
  Clock 0:00.0     0x07     unchanged
  Signal button    0x07     unchanged

Timeout is the only event that changes pos 8/9. Clock 0:00 and signal
button both activate pos 15 alone with no count change.

0x07 is the ASCII BEL control character — the same byte that historically
drove a terminal bell. Here it drives the physical buzzer on the scoreboard.

### Unknown

  Pos  Field               Notes
  ---  -----------------   -----------------------------------------
  0    Always 0x30         likely shot clock — constant 00 when
  1    Always 0x30         no shot clock unit is connected

---

## Frame Map (baseline state)

  pos:  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20
  hex: 30  30  20  30  20  30  31  20  30  30  30  20  20  30  30  20  20  20  30  20  30
  chr:  0   0   _   0   _   0   1   _   0   0   0   _   _   0   0   _   _   _   0   _   0

  Meaning at baseline:
  - Home score:  0 (pos 16+17+18 = space+space+0)
  - Guest score: 0 (pos 12+11+10 = space+space+0)
  - Home fouls:  0 (pos 2+3 = space+0)
  - Away fouls:  0 (pos 4+5 = space+0)
  - Period:      1 (pos 6 = 1)
  - Clock:       0:00 stopped
  - Possession:  none (pos 7 = space)
  - Buzzer:      off (pos 15 = 0x20)

---

## Annotated Example Frame

Home score 11, guest score 6, home fouls 1, away fouls 3, period 1,
clock 5:53 stopped, no possession:

  Hex: 303020312033312030303620203535202031312035

  pos: 0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20
  hex: 30  30  20  31  20  33  31  20  30  30  36  20  20  33  35  20  20  31  31  20  35
  chr:  0   0   _   1   _   3   1   _   0   0   6   _   _   3   5   _   _   1   1   _   5

  home_score  = space + 1 + 1 = 11     (pos 16+17+18)
  guest_score = space + space + 6 = 6  (pos 12+11+10)
  home_fouls  = space + 1 = 1          (pos 2+3)
  away_fouls  = space + 3 = 3          (pos 4+5)
  period      = 1                      (pos 6)
  possession  = none                   (pos 7 = space)
  minutes     = 5                      (pos 20)
  seconds     = tens(5) + units(3) = 53  (pos 14+13)
  clock       = 5:53 stopped

---

## Sub-second Transition Example

Frame at 0:59.9 (transition from normal to tenths mode):

  pos 13: 0x30 -> 0x20  (space — tenths mode activated)
  pos 14: 0x30 -> 0x39  (9 — tenths start at 9)
  pos 19: 0x20 -> 0x35  (5 — seconds tens)
  pos 20: 0x31 -> 0x39  (9 — seconds units)
  result: 0:59.9

---

## Capture Tool

    python3 capture.py --port /dev/tty.usbserial-XXXX

Reads frames using read_until(carriage return) for frame alignment.
Labels frames interactively when ENTER is pressed.
Output saved to timestamped log file.

---

## Notes

- The frame is a display buffer — it reflects exactly what the physical
  scoreboard shows, not an abstract data structure.
- ASCII encoding makes frames human-readable without a decoder.
- 0x07 (BEL) at pos 15 drives the physical buzzer — not a digit.
- Positions 0+1 are always 0x30 — likely shot clock value, constant 00
  when no shot clock unit is connected.
- Pos 7 is a possession indicator (jump ball arrow), not a timeout flag.
- The AK30-IPF has personal foul panels — positions not yet documented
  as the panels were not connected during capture sessions.
- Maximum period is 5 (OT). Anatec does not support multiple overtime periods.
- Scores above 199 not tested.
- Frame alignment is critical — always read until carriage return,
  do not slice raw byte stream into fixed chunks.
- Running detection requires comparing consecutive frames — no single
  frame contains an unambiguous running flag.