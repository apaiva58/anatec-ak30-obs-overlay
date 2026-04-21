#####################################################################
# Anatec AK30 Protocol Capture Script
# 
# Purpose: Discover and document the Anatec AK30 serial protocol
#          by capturing and labelling raw frames from the controller.
#
# Usage:
#   1. Connect Anatec AK30 controller via USB
#   3. Run: python3 capture.py --port /dev/tty.usbserial-XXXX
#   4. Operate the controller and press ENTER to label each action
#
# Output:
#   - Live frame display in terminal
#   - Annotated log file saved automatically
#
# Author: Almere Pioneers Basketball
# Based on: github.com/remcoenden/vMixScoreboard
#####################################################################

import serial
import sys
import datetime
import select
import tty
import termios

#####################################################################
# Configuration
#####################################################################
import argparse

_ap = argparse.ArgumentParser()
_ap.add_argument("--port", default="/dev/tty.usbserial-1110",
                 help="Serial port (run: ls /dev/tty.* to find yours)")
_ap.add_argument("--baud", type=int, default=2400)
_args = _ap.parse_args()

PORT = _args.port
BAUD = _args.baud

#####################################################################
# Session log
#####################################################################
LOG_FILE = f"anatec_capture_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

def log(msg, also_print=True):
    with open(LOG_FILE, 'a') as f:
        f.write(msg + '\n')
    if also_print:
        print(msg)

#####################################################################
# Frame formatting
#####################################################################
def format_frame(frame, label=""):
    lines = []
    lines.append(f"\n{'='*55}")
    if label:
        lines.append(f"  ACTION: {label}")
    lines.append(f"  Time:    {datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    lines.append(f"  Hex:     {frame.hex()}")
    lines.append(f"  Length:  {len(frame)} bytes")
    lines.append(f"  {'Pos':<5} {'Hex':<6} {'Dec':<5} {'Chr'}")
    lines.append(f"  {'-'*32}")
    for i, b in enumerate(frame):
        char = chr(b) if 32 <= b <= 126 else '.'
        lines.append(f"  {i:<5} {hex(b):<6} {b:<5} {char}")
    lines.append(f"{'='*55}")
    return '\n'.join(lines)

def format_diff(old_frame, new_frame):
    if old_frame is None or len(old_frame) != len(new_frame):
        return ""
    changes = [
        (i, old_frame[i], new_frame[i])
        for i in range(len(old_frame))
        if old_frame[i] != new_frame[i]
    ]
    if not changes:
        return ""
    lines = ["\n  *** CHANGED BYTES ***"]
    for i, old, new in changes:
        old_c = chr(old) if 32 <= old <= 126 else '.'
        new_c = chr(new) if 32 <= new <= 126 else '.'
        lines.append(
            f"  pos {i:<3} {hex(old):<6}({old_c}) → "
            f"{hex(new):<6}({new_c})  dec: {old} → {new}"
        )
    return '\n'.join(lines)

#####################################################################
# Session protocol — what to test
#####################################################################
SESSION_GUIDE = """
SESSION PROTOCOL — operate the controller in this order,
pressing ENTER after each action to label it:

  1.  Baseline — everything at zero
  2.  +1 home score
  3.  +1 guest score
  4.  Start clock
  5.  Stop clock (note the seconds value)
  6.  Period +1 (to period 2)
  7.  Period +1 (to period 3)
  8.  Team foul home +1
  9.  Team foul guest +1
  10. Timeout home (TOT1)
  11. Timeout home again (TOT2)
  12. Timeout guest (TOG1)
  13. Reset t.o. (all timeouts reset)
  14. Service dot home ON
  15. Service dot home OFF
  16. Signal button (probably no change)
  17. Shot clock reset to 24
  18. Personal foul player 5 home (if panels connected)

Press ENTER after each action to label it in the log.
Press CTRL+C when done.
"""

#####################################################################
# Main
#####################################################################
def main():
    print(f"\n{'#'*55}")
    print(f"  Anatec AK30 Protocol Capture")
    print(f"  Almere Pioneers Basketball")
    print(f"{'#'*55}")
    print(f"\n  Port:     {PORT}")
    print(f"  Baud:     {BAUD}")
    print(f"  Log file: {LOG_FILE}")
    print(SESSION_GUIDE)

    log(f"=== Anatec AK30 Capture Session ===")
    log(f"Port: {PORT} @ {BAUD} baud")
    log(f"Started: {datetime.datetime.now()}\n")
    log(SESSION_GUIDE, also_print=False)

    try:
        ser = serial.Serial(PORT, BAUD, timeout=2)
    except Exception as e:
        print(f"Could not open port: {e}")
        print(f"\nAvailable ports — run: ls /dev/tty.*")
        sys.exit(1)

    print("  Listening... operate the controller.")
    print("  Press ENTER to label an action.\n")

    last_frame = None
    frame_count = 0

    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

    try:
        while True:
            # Check for ENTER key (non-blocking)
            if select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1)
                if key in ('\n', '\r'):
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                    label = input("  → Label this action: ").strip()
                    tty.setcbreak(sys.stdin.fileno())
                    if label and last_frame is not None:
                        msg = format_frame(last_frame, label)
                        log(msg)
                        print(f"  ✓ Labeled: '{label}'")

            # Read next frame
            raw = ser.read_until(b'\r')
            if not raw:
                print("  [no data — check USB connection]")
                continue

            # Strip terminator
            frame = raw.rstrip(b'\r').rstrip(b'\n')

            # Also check for { } delimited frames (per README)
            if b'{' in raw and b'}' in raw:
                start = raw.index(b'{')
                end = raw.index(b'}')
                if end > start:
                    frame = raw[start+1:end]
                    print("  [{ } frame format detected]")

            if not frame:
                continue

            frame_count += 1

            if frame != last_frame:
                diff = format_diff(last_frame, frame)
                output = f"Frame #{frame_count} | {frame.hex()}"
                if diff:
                    output += diff
                print(output)
                log(output, also_print=False)
                last_frame = frame
            else:
                if frame_count % 20 == 0:
                    print('.', end='', flush=True)

    except KeyboardInterrupt:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        log(f"\n=== Session ended — {frame_count} frames captured ===")
        print(f"\n\nStopped. {frame_count} frames captured.")
        print(f"Log saved to: {LOG_FILE}")
        ser.close()

if __name__ == "__main__":
    main()
