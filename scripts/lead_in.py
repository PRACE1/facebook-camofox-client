"""Countdown lead-in: hit Record, get ready, action starts hands-free.

Clears the screen, counts N..1 big, beeps the last 3, then runs the command.
For Cap/screen-recorder users who need hands off the keyboard when it starts.

Usage (CMD):
  python scripts\\lead_in.py 15 -- python scripts\\run_marketplace_create_dryrun.py
"""
import subprocess
import sys
import time


def main() -> int:
    if "--" not in sys.argv or len(sys.argv) < 4:
        print("usage: python scripts\\lead_in.py <seconds> -- <command...>")
        return 2
    try:
        total = max(3, min(60, int(sys.argv[1])))
    except ValueError:
        print("seconds must be a number (3-60).")
        return 2
    cmd = sys.argv[sys.argv.index("--") + 1:]
    for n in range(total, 0, -1):
        print("\n" * 2 + f"   Starting in {n} ...")
        if n <= 3:
            try:
                import winsound

                winsound.Beep(880 if n > 1 else 1320, 180)
            except Exception:
                pass
        time.sleep(1)
    print("GO.")
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
