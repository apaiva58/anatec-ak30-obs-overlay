# anatec-ak30-obs-overlay

## Purpose

Almere Pioneers Basketball streams and records live games through OBS Studio.
This project provides an automatic scoreboard overlay for those streams —
so the score, clock, fouls and timeouts appear on screen without anyone
manually updating them during the game.

The scoreboard operator works the Anatec AK30 controller as normal.
The DWF tablet operator enters the game data as normal.
The overlay updates itself.

Developed by dr. Antonio Paiva Aranda for Almere Pioneers Basketball (Almere, The Netherlands).

---

## What it does

Reads live scoreboard data from two sources:

- Anatec AK30 serial feed — score, clock, period, fouls, timeouts direct from the controller via USB
- FOYS DWF API — live match data from the NBB Digitaal Wedstrijd Formulier system, including player names, fouls per player, and match roster

Serves both data sources as a web overlay for OBS Studio Browser Source.
One person operates the scoreboard as normal — the overlay updates automatically.

---

## Features

- Live score, period, clock and team fouls
- Timeout popup with 60-second flash
- Bonus situation indicator (4+ team fouls)
- Foul popup with player name and jersey number
- Automatic transition to final stats table at match end
- Player points, 3-pointers and fouls in final summary
- Match selection UI — volunteer selects the correct match from a phone browser
- Works with Anatec serial only, FOYS only, or both combined

---

## Project Status

| Milestone | Status |
|---|---|
| 1. Protocol discovery | done |
| 2. Serial reader and parser | done |
| 3. Flask server and OBS overlay | done |
| 4. FOYS DWF API integration | done |
| 5. Final stats overlay | done |
| 6. Second capture session (multi-digit scores) | planned |
| 7. OBS integration test at the hall | planned |
| 8. Raspberry Pi deployment | under consideration |
| 9. Community / other clubs | planned |

---

## Hardware

### Minimum setup
- Anatec AK30 scoreboard controller (any variant)
- USB-A to USB-B cable from controller to laptop
- MacBook or laptop running Python 3.8+ and OBS Studio

### If USB port is unavailable
Tap the DIN 5-pin connector between controller and display board using:
- DIN 5-pin male to open-end cable
- FTDI FT232RL USB-to-serial adapter (5V tolerant)

See docs/hardware.md for full wiring instructions.

### Supported hardware
Developed and tested with:
- Anatec AK30-IPF (with personal foul panels)

Likely compatible with:
- Anatec AK30-I (without personal foul panels)
- Other Anatec AK30 variants

---

## Requirements

- Python 3.8+
- pyserial, flask, requests, python-dotenv
- OBS Studio with Browser Source support (https://obsproject.com)

Install dependencies:

    pip3 install -r requirements.txt --break-system-packages

---

## Quick Start

    # 1. Install dependencies
    pip3 install -r requirements.txt --break-system-packages

    # 2. Copy .env.example to .env and fill in FOYS credentials
    cp .env.example .env

    # 3. Connect Anatec AK30 via USB and find the port
    ls /dev/tty.*

    # 4. Run the server (simulate mode — no hardware needed)
    python3 scoreboard/server.py --anatec simulate

    # 5. Run the server with real Anatec hardware
    python3 scoreboard/server.py --anatec serial --port /dev/tty.usbserial-XXXX

    # 6. Run without Anatec (FOYS only)
    python3 scoreboard/server.py --anatec off

    # 7. Use demo environment
    python3 scoreboard/server.py --anatec off --demo

    # 8. Open match selection in browser
    http://localhost:5001

    # 9. Add overlay as OBS Browser Source
    http://localhost:5001/overlay

---

## Repository Structure

    anatec-ak30-obs-overlay/
    ├── README.md                   this file
    ├── requirements.txt            Python dependencies
    ├── capture.py                  protocol discovery script
    ├── scoreboard/
    │   ├── foys.py                 FOYS DWF API client
    │   ├── reader.py               Anatec serial reader
    │   ├── parser.py               Anatec frame parser
    │   ├── simulator.py            game simulator for testing
    │   ├── server.py               Flask server and API endpoints
    │   └── state.py                shared in-memory match state
    ├── templates/
    │   ├── select.html             match selection UI
    │   ├── overlay.html            combined live and final overlay for OBS
    │   ├── overlay_foys.html       FOYS-only overlay
    │   └── overlay_anatec.html     Anatec-only overlay
    └── docs/
        ├── protocol.md             Anatec AK30 serial frame format
        ├── foys-api.md             FOYS DWF API reference
        ├── foys-overlay.md         FOYS overlay integration guide
        ├── hardware.md             connectors, wiring, Pi setup
        └── setup.md                volunteer setup guide

---

## How it works

### Anatec serial

The Anatec AK30 controller continuously transmits scoreboard state over serial
at 2400 baud. Each frame is 23 bytes (21 data bytes + CR terminator), ASCII encoded. Byte positions carry
score, clock, period, fouls, timeouts and service dot state.

The serial protocol was reverse-engineered from the Anatec AK30-IPF controller
via a capture session at the hall. See docs/protocol.md for the full frame format.

### FOYS DWF API

The NBB uses FOYS as its match management system. The DWF tablet app sends
live match events to api.foys.io. This project polls three endpoints every
3 seconds:

    /matches/{id}/goals       score calculation
    /matches/{id}/offenses    team fouls and player fouls
    /matches/{id}/timeouts    timeout count per team per period

See docs/foys-api.md for the full API reference.

### Overlay

A Flask server combines both data sources into a single /api/state endpoint.
The OBS Browser Source loads overlay.html which polls /api/state every 3 seconds
and updates the display. At match end the scorebar automatically transitions
to a final stats table.

---

## Credentials

FOYS API requires authentication using credentials issued by NBB at club level.
Not every club member has DWF access — credentials are managed by the club
administrator via the NBB backend.

It is recommended to create a dedicated streaming account separate from the
main DWF operator account. This allows the streaming credential to be managed
independently and makes troubleshooting easier. Contact your NBB club
administrator to request a dedicated account.

Create a .env file — never commit to git:

    FOYS_USERNAME=...
    FOYS_PASSWORD=...
    FOYS_ORGANISATION_ID=...
    FOYS_ORGANISATION_ID_DEMO=...
    FOYS_DEMO_MODE=false

---

## Contributing

Contributions welcome — especially from other Dutch basketball clubs using
Anatec scoreboards or the FOYS DWF system.

If you have a different Anatec model and the byte positions differ, please
open an issue or submit a PR updating docs/protocol.md.

---

## License

MIT License — free to use, modify and distribute.

---

## Club

Almere Pioneers Basketball
Almere, The Netherlands
https://almerepioneers.nl

Development: dr. Antonio Paiva Aranda

---

## Acknowledgements

- Remco van den Enden — github.com/remcoenden/vMixScoreboard
  for the Anatec serial reader foundation
- Anatec B.V. — AK30 scoreboard hardware
- FOYS / NBB Basketball Nederland — DWF match management system