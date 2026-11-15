"""Standalone check that the Pi's audio output can play the alarm sound.

Not imported by the app. Run by hand:

    python backend/experiments/alarm_test.py              # system default audio device
    python backend/experiments/alarm_test.py -D plughw:CARD=UACDemoV10,DEV=0

It plays the bundled tone through `aplay` (ALSA), so it proves the speaker path
without a browser. `aplay -L` lists the device names `-D` accepts.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ALARM = Path(__file__).resolve().parents[2] / "frontend" / "src" / "assets" / "alarm.wav"
PLAY_SECONDS = 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-D", "--device", help="ALSA device name passed to aplay -D")
    args = parser.parse_args()

    if not ALARM.is_file():
        print(f"Alarm file not found: {ALARM}", file=sys.stderr)
        return 1

    cmd = ["aplay", "-q", "-d", str(PLAY_SECONDS)]
    if args.device:
        cmd += ["-D", args.device]
    cmd.append(str(ALARM))

    print(f"Playing {ALARM.name} for up to {PLAY_SECONDS}s: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd)
    except FileNotFoundError:
        print("aplay not found (install alsa-utils)", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(f"aplay exited with code {result.returncode}", file=sys.stderr)
        if not args.device:
            print("The default ALSA device may not be the speaker; see `aplay -l` / `aplay -L` and retry with -D.", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
