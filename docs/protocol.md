# Anatec AK30 Serial Protocol

Captured: 2026-04-20, Almere Pioneers hall session  
Hardware: Anatec AK30-IPF  
Connection: USB-B → USB-A via /dev/tty.usbserial-1110  
Baud rate: 2400, 8N1  

---

## Frame Format

The controller transmits a continuous stream of 21-byte frames.

All values are **ASCII encoded** — the digit `0` is transmitted as `0x30`, 
`1` as `0x31`, etc. Spaces (`0x20`) act as separators or represent 
empty/zero fields.

```
Baseline frame (all zero, clock stopped):
30 30 20 30 20 30 30 20 30 30 30 20 20 30 30 20 20 20 30 20 30
 0  0  _  0  _  0  0  _  0  0  0  _  _  0  0  _  _  _  0  _  0
pos: 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20
```

---

## Byte Position Map

| Pos | Field | Values |
|-----|-------|--------|
| 0–1 | Unknown | always `30 30` |
| 2   | Separator | `0x20` |
| 3   | **Home team fouls** | ASCII digit: `0x30`=0, `0x31`=1, `0x32`=2... |
| 4   | Separator | `0x20` |
| 5   | **Guest fouls — tens** | ASCII digit |
| 6   | **Guest fouls — units** | ASCII digit |
| 7   | **Timeout active flag** | `0x54`='T' home, `0x47`='G' guest, `0x20`=none |
| 8   | **Guest timeout blink** | blinks `0x30`/`0x31` during guest timeout |
| 9   | **Home timeout blink** | blinks `0x30`/`0x31` during home timeout |
| 10  | **Guest score** | ASCII digit: `0x30`=0, `0x31`=1... |
| 11  | Separator | `0x20` |
| 12  | Separator | `0x20` |
| 13  | **Clock seconds — tens** | ASCII digit: `0x36`=6, `0x35`=5... |
| 14  | **Clock seconds — units** | ASCII digit: `0x35`=5, `0x34`=4... |
| 15  | **Shot clock / service dot** | `0x07`=ON, `0x20`=OFF |
| 16  | Separator | `0x20` |
| 17  | Separator | `0x20` |
| 18  | **Home score** | ASCII digit: `0x30`=0, `0x31`=1... |
| 19  | **Clock minutes — tens** | `0x20`=0–9 min, `0x31`=10–19 min |
| 20  | **Clock minutes — units** | ASCII digit, also signals clock running |

---

## Clock Encoding

The clock counts **down** from 10:00 (period start).

- Minutes: pos 19 (tens) + pos 20 (units)
- Seconds: pos 13 (tens) + pos 14 (units)

Example — clock showing 9:35:
```
pos 19 = 0x20 (space = tens digit 0, so 0–9 range)
pos 20 = 0x39 ('9')
pos 13 = 0x33 ('3')
pos 14 = 0x35 ('5')
→ time = 9:35
```

Example — clock showing 1:28:
```
pos 19 = 0x20
pos 20 = 0x31 ('1')
pos 13 = 0x32 ('2')
pos 14 = 0x38 ('8')
→ time = 1:28
```

Clock running indicator: pos 20 = `0x31` when clock is running.  
Clock stopped: pos 20 = `0x30`.

**Note**: The clock running/stopped state partially overlaps with 
the minutes units digit. Further verification needed for values 
above 1:xx when clock is running.

---

## Period

Period is encoded at **pos 6** alongside the guest fouls tens digit.

| pos 6 value | Meaning |
|-------------|---------|
| `0x30` | Period 1 (or not yet set) |
| `0x32` | Period 2 |
| `0x33` | Period 3 |

**Ambiguity**: pos 5+6 also encode guest team fouls. The combination 
`pos5=0x31, pos6=0x33` appeared after "team foul guest +1" in period 3.
This suggests the display shows a combined period+foul value 
(e.g. `13` = 1 foul in period 3).

This needs further verification with multiple fouls across periods.

---

## Team Fouls

**Home fouls** — pos 3, single ASCII digit:
- `0x30` = 0 fouls
- `0x31` = 1 foul
- etc.

**Guest fouls** — pos 5 (tens) + pos 6 (units), may encode period:
- `0x30 0x30` = 0 fouls
- `0x31 0x33` = observed after 1 foul in period 3

Needs further capture to fully decode guest foul + period encoding.

---

## Timeouts

**During a timeout:**
- pos 7 = `0x54` ('T') for home timeout, `0x47` ('G') for guest timeout
- pos 9 blinks rapidly between `0x30`/`0x31` (home)
- pos 8 blinks rapidly between `0x30`/`0x31` (guest)

**Timeout count** (after timeout ends):
- pos 9 = `0x31` after 1st home timeout used
- pos 9 = `0x32` after 2nd home timeout used
- pos 8 = `0x32` after guest timeout used

**Reset timeouts**: pos 8 and pos 9 return to `0x30`

---

## Scores

**Home score** — pos 18, single ASCII digit:
- `0x30` = 0
- `0x31` = 1
- etc.

**Guest score** — pos 10, single ASCII digit.

**Note**: Single digit only — scores above 9 need further capture.
For multi-digit scores, additional positions likely come into play.

---

## Shot Clock / Service Dot

- pos 15 = `0x07` when service dot is ON
- pos 15 = `0x20` when OFF
- Appears briefly during shot clock reset and timeout

---

## Observed Frames

```
State                    Frame
─────────────────────────────────────────────────────────
Baseline (all zero)      30 30 20 30 20 30 30 20 30 30 30 20 20 30 30 20 20 20 30 20 30
Home score = 1           30 30 20 30 20 30 30 20 30 30 30 20 20 30 30 20 20 20 31 20 30
Guest score = 1          30 30 20 30 20 30 30 20 30 30 31 20 20 30 30 20 20 20 31 20 30
Clock running 9:65       30 30 20 30 20 30 30 20 30 30 31 20 20 36 35 20 20 20 31 20 31
Clock stopped 9:60       30 30 20 30 20 30 30 20 30 30 31 20 20 36 30 20 20 20 31 20 31
Period 2                 30 30 20 30 20 30 32 20 30 30 31 20 20 36 30 20 20 20 31 20 31
Period 3                 30 30 20 30 20 30 33 20 30 30 31 20 20 36 30 20 20 20 31 20 31
Guest foul (period 3)    30 30 20 30 20 31 33 20 30 30 31 20 20 20 39 20 20 20 31 32 38
Home foul (period 3)     30 30 20 31 20 31 33 20 30 30 31 20 20 20 39 20 20 20 31 32 38
Home timeout active      30 30 20 31 20 31 33 20 30 31 31 20 20 30 30 07 20 20 31 20 30
Guest timeout active     30 30 20 31 20 31 33 20 30 32 31 20 20 30 30 07 20 20 31 20 30
Reset timeouts           30 30 20 31 20 31 33 20 30 30 31 20 20 30 30 20 20 20 31 20 30
```

---

## Open Questions

1. How are scores above 9 encoded? (pos 18/10 are single digits)
2. Guest foul + period encoding — is it truly combined in pos 5+6?
3. Clock running indicator vs minutes units digit — overlap at 1:xx?
4. Personal fouls (if AK30-IPF panels connected) — which positions?
5. Shot clock value — is it transmitted or just the on/off flag?

---

## Parser Implementation

```python
def parse_frame(frame: bytes) -> dict:
    """Parse a 21-byte Anatec AK30 frame."""
    if len(frame) != 21:
        return None
    
    def digit(pos):
        v = frame[pos]
        return v - 0x30 if 0x30 <= v <= 0x39 else 0
    
    minutes = digit(20) + (digit(19) * 10 if frame[19] != 0x20 else 0)
    seconds = digit(13) * 10 + digit(14)
    
    return {
        "home_score":   digit(18),
        "guest_score":  digit(10),
        "home_fouls":   digit(3),
        "guest_fouls":  digit(6),          # units only — see open questions
        "period":       digit(6),          # ambiguous with guest fouls
        "clock_min":    minutes,
        "clock_sec":    seconds,
        "clock_running": frame[20] == 0x31,
        "timeout_active": chr(frame[7]) if frame[7] in (0x54, 0x47) else None,
        "service_dot":  frame[15] == 0x07,
    }
```

---

## References

- Remco van den Enden — vMixScoreboard: https://github.com/remcoenden/vMixScoreboard
- Anatec AK30-IPF manual: https://anatec.nl/wp-content/uploads/2019/07/Handleiding_bedieningsunit_met_persoonlijke_fouten_AK30_IPF_v10.1_.0_L_.pdf
- Capture session log: anatec_capture_20260420_180357.txt
