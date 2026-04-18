# Anatec AK30 Serial Protocol

This document describes the serial protocol used by the Anatec AK30 
scoreboard controller to transmit live scoreboard data.

Status: WORK IN PROGRESS — to be completed after capture session.

---

## Connection parameters

- Protocol:   UART serial, 8N1
- Baud rate:  2400
- Data bits:  8
- Stop bits:  1
- Parity:     None
- Connector:  USB-B or DIN 5-pin (see docs/hardware.md)

---

## Frame format

Each frame is a complete snapshot of the current scoreboard state.

- Length:     23 bytes
- Terminator: carriage return (0x0D)
- Delimiter:  possibly { start } end (to be confirmed)

The controller transmits frames continuously while powered on.
The display updates on each received frame.

---

## Known byte positions

Based on AnatecIndor.py by Remco van den Enden.
Byte positions are 0-indexed.

    Pos       Field           Notes
    -------   -------------   ---------------------------
    0 - 1     Shot clock      2 digits
    10 - 11   Guest score     reversed: [11] + [10]
    13 - 14   Seconds         reversed: [14] + [13]
    17 - 18   Home score      2 digits
    19 - 20   Minutes         2 digits

---

## Unknown byte positions

To be determined during capture session at the hall.

    Pos       Field           Status
    -------   -------------   ---------------------------
    2         ?               unknown
    3         ?               unknown
    4         ?               unknown
    5         ?               unknown
    6         ?               unknown
    7         ?               unknown
    8         ?               unknown
    9         ?               unknown
    12        ?               unknown
    15        ?               unknown
    16        ?               unknown
    21        ?               unknown
    22        ?               unknown

Suspected fields in unknown bytes:
- Period (1-4)
- Team fouls home (0-9)
- Team fouls guest (0-9)
- Timeouts home (0-3)
- Timeouts guest (0-3)
- Service dot home (0/1)
- Service dot guest (0/1)
- Clock direction (up/down)
- Clock running state (running/stopped)

---

## Capture session findings

TO BE COMPLETED.

Session date: 
Controller model: Anatec AK30-IPF
Location: 

### Action log

Each entry shows which bytes changed when an action was performed
on the controller.

1. Baseline (everything at zero)
   Frame: 
   Notes: 

2. +1 home score
   Changed bytes: 
   Notes: 

3. +1 guest score
   Changed bytes: 
   Notes: 

4. Start clock
   Changed bytes: 
   Notes: 

5. Stop clock
   Changed bytes: 
   Notes: 

6. Period +1 (to period 2)
   Changed bytes: 
   Notes: 

7. Period +1 (to period 3)
   Changed bytes: 
   Notes: 

8. Team foul home +1
   Changed bytes: 
   Notes: 

9. Team foul guest +1
   Changed bytes: 
   Notes: 

10. Timeout home (TOT1)
    Changed bytes: 
    Notes: 

11. Timeout home again (TOT2)
    Changed bytes: 
    Notes: 

12. Timeout guest (TOG1)
    Changed bytes: 
    Notes: 

13. Reset t.o. (all timeouts reset)
    Changed bytes: 
    Notes: 

14. Service dot home ON
    Changed bytes: 
    Notes: 

15. Service dot home OFF
    Changed bytes: 
    Notes: 

16. Signal button
    Changed bytes: 
    Notes: 

17. Shot clock reset to 24
    Changed bytes: 
    Notes: 

18. Personal foul player 5 home
    Changed bytes: 
    Notes: 

---

## Complete byte map (to be filled in)

    Pos       Field                   Value encoding
    -------   ---------------------   ------------------
    0         Shot clock digit 1      ASCII digit
    1         Shot clock digit 2      ASCII digit
    2         ?                       
    3         ?                       
    4         ?                       
    5         ?                       
    6         ?                       
    7         ?                       
    8         ?                       
    9         ?                       
    10        Guest score digit 2     ASCII digit
    11        Guest score digit 1     ASCII digit
    12        ?                       
    13        Seconds digit 2         ASCII digit
    14        Seconds digit 1         ASCII digit
    15        ?                       
    16        ?                       
    17        Home score digit 1      ASCII digit
    18        Home score digit 2      ASCII digit
    19        Minutes digit 1         ASCII digit
    20        Minutes digit 2         ASCII digit
    21        ?                       
    22        ?                       
    23        Terminator              0x0D (carriage return)

---

## References

- AnatecIndor.py: github.com/remcoenden/vMixScoreboard
- Anatec AK30-IPF manual: anatec.nl
- Capture log: anatec_capture_YYYYMMDD_HHMMSS.txt
