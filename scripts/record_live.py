"""Record the live desktop while a command runs — genuine mouse footage.

Starts ffmpeg gdigrab on the desktop, runs the target command, stops capture.
Use for the next live run so the demo shows the real mouse moving/typing.

Usage (CMD):
  python scripts\\record_live.py artifacts\\live_run.mp4 -- python scripts\\run_marketplace_create_dryrun.py
Output: the given mp4 path (gitignored dirs recommended).
Windows-only (gdigrab). Stop: command exit stops capture automatically.
"""
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        print("usage: python scripts\\record_live.py <out.mp4> -- <command...>")
        return 2
    out, cmd = sys.argv[1], sys.argv[3:]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cap = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "gdigrab", "-framerate", "30", "-i", "desktop",
         "-pix_fmt", "yuv420p", out])
    try:
        r = subprocess.run(cmd)
        code = r.returncode
    finally:
        cap.terminate()
        try:
            cap.wait(timeout=10)
        except Exception:
            cap.kill()
    print(f"footage: {out} (cmd exit {code})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
