# Setup Guide

This guide explains how to set up the Anatec AK30 OBS overlay 
from scratch on a MacBook.

---

## What you need

- MacBook running macOS 11 or later
- Anatec AK30 scoreboard controller
- USB-A to USB-B cable (standard printer cable)
- OBS Studio installed (https://obsproject.com)
- Python 3.8 or later installed

---

## Step 1 — Check Python

Open Terminal (Applications -> Utilities -> Terminal) and run:

    python3 --version

You should see something like:

    Python 3.11.2

If Python is not installed, download it from https://python.org

---

## Step 2 — Download the project

Option A — download as ZIP:
1. Go to https://github.com/YOUR-USERNAME/anatec-ak30-obs-overlay
2. Click the green Code button
3. Click Download ZIP
4. Unzip to your Documents folder

Option B — clone with Terminal:

    cd ~/Documents
    git clone https://github.com/YOUR-USERNAME/anatec-ak30-obs-overlay.git

---

## Step 3 — Install dependencies

In Terminal, navigate to the project folder:

    cd ~/Documents/anatec-ak30-obs-overlay

Install required Python packages:

    pip3 install -r requirements.txt

You should see:

    Successfully installed flask pyserial

---

## Step 4 — Connect the controller

1. Power on the Anatec AK30 controller
2. Connect it to your MacBook with the USB cable
3. In Terminal, run:

        ls /dev/tty.*

4. Note the port name that appears, for example:

        /dev/tty.usbserial-AB0PQRST

5. Open capture.py in a text editor and update the PORT line:

        PORT = '/dev/tty.usbserial-AB0PQRST'

---

## Step 5 — Verify the connection

Run the capture script:

    python3 capture.py

You should see frames appearing in the terminal as you operate 
the controller. If you see dots (......) the connection is working 
but nothing is changing — press some buttons on the controller.

If you see "no data — check USB connection", the port name is 
wrong or the controller USB is not active. See docs/hardware.md 
for the DIN 5-pin alternative.

Press CTRL+C to stop the capture script.

---

## Step 6 — Run the scoreboard bridge

Once the connection is verified:

    python3 scoreboard/server.py --port /dev/tty.usbserial-AB0PQRST

You should see:

    Scoreboard bridge running at http://localhost:5000
    Connected to Anatec AK30 on /dev/tty.usbserial-AB0PQRST
    Listening...

Leave this Terminal window open. The bridge must keep running 
during the match.

---

## Step 7 — Verify the overlay

Open a browser and go to:

    http://localhost:5000/overlay

You should see the scoreboard overlay. Operate the controller 
and verify the overlay updates automatically.

To check the raw data feed:

    http://localhost:5000/data

You should see something like:

    {
        "home": "42",
        "guest": "38",
        "minutes": "08",
        "seconds": "24",
        "shotClock": "18",
        "period": "3",
        "foulsHome": "4",
        "foulsGuest": "3",
        "timeoutsHome": "1",
        "timeoutsGuest": "0"
    }

---

## Step 8 — Set up OBS

1. Open OBS Studio
2. In the Sources panel, click the + button
3. Select Browser
4. Name it Scoreboard Overlay and click OK
5. In the URL field enter:

        http://localhost:5000/overlay

6. Set Width to 1920 and Height to 1080
7. Click OK

The scoreboard overlay now appears in OBS. Position and resize 
it as needed over your camera feed.

This Browser Source URL never changes — OBS is configured once 
and works every match automatically.

---

## Match day checklist

Before each match:

    [ ] Power on Anatec AK30 controller
    [ ] Connect USB cable to MacBook
    [ ] Open Terminal
    [ ] Run: python3 scoreboard/server.py --port /dev/tty.usbserial-XXXX
    [ ] Verify overlay at http://localhost:5000/overlay
    [ ] Open OBS — overlay should be visible
    [ ] Start stream in OBS

During the match:

    [ ] Operate the Anatec controller as normal
    [ ] Overlay updates automatically
    [ ] No manual score input needed

After the match:

    [ ] Stop stream in OBS
    [ ] Press CTRL+C in Terminal to stop the bridge
    [ ] Disconnect USB cable

---

## Troubleshooting

Problem: ls /dev/tty.* shows nothing after connecting the controller
Solution: The controller USB port may not be active without the Anatec
          hardware modification. See docs/hardware.md for the DIN 5-pin 
          alternative.

Problem: Overlay shows but values do not update
Solution: Check the Terminal window for errors. Verify the controller 
          is powered on and the USB cable is connected.

Problem: OBS Browser Source shows blank page
Solution: Make sure the bridge is running (Terminal window open with 
          server.py). The bridge must be running before OBS can 
          display the overlay.

Problem: Values are wrong (score shows as time etc.)
Solution: The byte positions in parser.py may differ for your 
          controller model. Run capture.py and compare with 
          docs/protocol.md. Open an issue on GitHub if your 
          model differs.

Problem: Port name changes every time I plug in
Solution: On macOS the port name can change. Always run ls /dev/tty.* 
          after connecting to get the current port name. The packaged 
          app (Milestone 3) will detect the port automatically.

---

## Getting help

- Open an issue: https://github.com/YOUR-USERNAME/anatec-ak30-obs-overlay/issues
- Check docs/hardware.md for wiring details
- Check docs/protocol.md for frame format details

---

## For other clubs

If you use a different Anatec controller model and the byte positions 
differ from docs/protocol.md, please open an issue or submit a pull 
request with your findings. The goal is to document the full range 
of Anatec AK30 variants for the Dutch basketball community.
