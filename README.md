# anatec-ak30-obs-overlay

A Python bridge between the Anatec AK30 scoreboard controller and OBS Studio, 
enabling live scoreboard overlays for basketball livestreams without manual score input.

## What it does

Reads live scoreboard data directly from the Anatec AK30 controller via USB, 
serves it as a web overlay, and feeds it into OBS Studio as a Browser Source. 
One person operates the scoreboard as normal — the overlay updates automatically.

## Background

Developed by Almere Pioneers basketball club (Almere, Netherlands) to automate 
scoreboard overlays for livestreamed matches. The Anatec AK30 controller outputs 
live scoreboard data via USB serial at 2400 baud. This project reads that data, 
parses it, and serves it as a live web overlay for OBS Studio.

The serial protocol was reverse-engineered from the Anatec AK30-IPF controller. 
Credit to Remco van den Enden (github.com/remcoenden/vMixScoreboard) whose work 
on the AnatecIndor serial reader provided the foundation for this project.

## Hardware

### Minimum setup
- Anatec AK30 scoreboard controller (any variant)
- USB cable (USB-A to USB-B) from controller to laptop
- MacBook or laptop running OBS Studio

### If USB is unavailable (older controller models)
Tap the DIN 5-pin connector between controller and display board using:
- DIN 5-pin male to open-end cable
- FTDI FT232RL USB-to-serial adapter (5V tolerant)

See docs/hardware.md for full wiring instructions.

## Project Status

| Milestone | Status |
|---|---|
| 1. Protocol discovery | 🔄 In progress |
| 2. Technical version (terminal) | ⏳ Planned |
| 3. Packaged macOS app | ⏳ Planned |
| 4. Extended features | ⏳ Planned |
| 5. Community / other clubs | ⏳ Planned |

## Roadmap

### Milestone 1 — Protocol Discovery
- [ ] USB connection test at the hall
- [ ] Capture session with capture.py
- [ ] Document all byte positions (score, time, period, fouls, timeouts)
- [ ] Publish protocol.md

### Milestone 2 — Technical Version
- [ ] Serial reader module
- [ ] Frame parser module
- [ ] Flask server + JSON endpoint
- [ ] HTML/CSS overlay with Pioneers branding
- [ ] OBS Browser Source integration test
- [ ] End-to-end test at the hall

### Milestone 3 — Packaged macOS App
- [ ] Simple GUI window (auto-detect USB, status display)
- [ ] Bundle as .app with PyInstaller
- [ ] Test on a second Mac
- [ ] Volunteer setup guide

### Milestone 4 — Extended Features
- [ ] Period display
- [ ] Team fouls display
- [ ] Timeouts display
- [ ] Personal fouls display
- [ ] Pioneers branding refinement
- [ ] Consider Windows version for other clubs

### Milestone 5 — Community
- [ ] Contact Remco van den Enden
- [ ] Publish full protocol documentation
- [ ] README for other Dutch basketball clubs using Anatec scoreboards
- [ ] Share with NBB / Sportlink community

## Supported Hardware

Developed and tested with:
- Anatec AK30-IPF (with personal foul panels)

Likely compatible with:
- Anatec AK30-I (without personal foul panels)
- Other Anatec AK30 variants

## Requirements

- Python 3.8+
- pyserial
- Flask
- OBS Studio with Browser Source support (https://obsproject.com)

Install Python dependencies with:

    pip3 install -r requirements.txt

## Quick Start

    # 1. Install dependencies
    pip3 install -r requirements.txt

    # 2. Connect Anatec AK30 via USB

    # 3. Discover your serial port
    ls /dev/tty.*

    # 4. First time: run protocol capture to verify connection
    python3 capture.py

    # 5. Run the bridge
    python3 scoreboard/server.py --port /dev/tty.usbserial-XXXX

## Repository Structure

    anatec-ak30-obs-overlay/
    ├── README.md                   — this file
    ├── requirements.txt            — Python dependencies
    ├── capture.py                  — protocol discovery script
    ├── scoreboard/
    │   ├── reader.py               — serial reader
    │   ├── parser.py               — frame parser
    │   └── server.py               — Flask server + JSON endpoint
    ├── overlay/
    │   ├── index.html              — OBS Browser Source overlay
    │   ├── style.css               — Pioneers branding
    │   └── script.js               — live data refresh
    └── docs/
        ├── protocol.md             — Anatec AK30 frame format
        ├── hardware.md             — connectors, wiring, FTDI approach
        └── setup.md                — full setup guide for volunteers

## How it works

The Anatec AK30 controller continuously transmits scoreboard state over serial 
at 2400 baud. Each transmission is a frame of 23 bytes terminated by a carriage 
return. The frame contains score, time, shot clock, period, fouls, and timeout 
state packed into specific byte positions.

This project reads those frames, parses the relevant values, and serves them 
via a local Flask web server. OBS Studio adds the overlay page as a Browser 
Source — it polls the JSON endpoint every second and updates the display 
automatically.

See docs/protocol.md for the full frame format documentation.

## Contributing

Contributions welcome — especially from other clubs using Anatec scoreboards. 
If you have a different Anatec model and the byte positions differ, please open 
an issue or submit a PR updating docs/protocol.md.

## License

MIT License — free to use, modify and distribute.

## Club

Almere Pioneers Basketball  
Almere, Netherlands  
https://almerepioneersbball.nl

## Acknowledgements

- Remco van den Enden — github.com/remcoenden/vMixScoreboard
  for the AnatecIndor serial reader foundation
- Anatec B.V. — AK30 scoreboard hardware
