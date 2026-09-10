"""Record the live desktop while a command runs — genuine mouse footage.

Captures the whole desktop by default; pass --title to capture ONLY the
window whose title contains a substring (e.g. the automation browser),
or --crop W:H:X:Y to clip a region. Keeps terminal/tabs/taskbar out.

Usage (CMD):
  python scripts\\record_live.py artifacts\\live_run.mp4 -- python scripts\\run_marketplace_create_dryrun.py
  python scripts\\record_live.py artifacts\\live_run.mp4 --title Facebook -- python scripts\\run_marketplace_create_dryrun.py
Output: the given mp4 path (gitignored dirs recommended).
Windows-only (gdigrab). Stop: command exit stops capture automatically.
"""
import subprocess
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    title, crop = None, None
    while args and args[0].startswith("--"):
        flag = args.pop(0)
        if flag == "--title":
            title = args.pop(0)
        elif flag == "--crop":
            crop = args.pop(0)
        else:
            print(f"unknown flag {flag}")
            return 2
    if "--" not in args or len(args) < 3:
        print("usage: python scripts\\record_live.py [--title SUB] [--crop W:H:X:Y] <out.mp4> -- <command...>")
        return 2
    out = args[0]
    cmd = args[2:]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    source = f"title={title}" if title else "desktop"
    grab = ["ffmpeg", "-y", "-f", "gdigrab", "-framerate", "30", "-i", source]
    if crop:
        grab += ["-vf", f"crop={crop}"]
    grab += ["-pix_fmt", "yuv420p", out]
    cap = subprocess.Popen(grab, stdin=subprocess.PIPE)
    try:
        r = subprocess.run(cmd)
        code = r.returncode
    finally:
        try:  # graceful 'q' finalizes the MP4 trailer; terminate() corrupts it
            cap.communicate(input=b"q", timeout=15)
        except Exception:
            cap.kill()
    print(f"footage: {out} (cmd exit {code})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
