"""Render a demo video from receipt screenshots — our own recap engine.

Stitches artifacts/receipts PNGs (or a chosen subset) into an MP4 timelapse:
each frame held ~1.5s, scaled to 1280 wide. No camera, no mic, no Cap.

Usage (CMD):
  python scripts\\receipts_to_video.py                 # all receipts, oldest first
  python scripts\\receipts_to_video.py after_publish form_filled   # name filter
Output: artifacts\\demo.mp4 (gitignored).
"""
import subprocess
import sys
from pathlib import Path

RECEIPTS = Path("artifacts/receipts")
OUT = Path("artifacts/demo.mp4")
FPS_FRAME_HOLD = 1.5
WIDTH = 1280


def main() -> int:
    filters = [a.lower() for a in sys.argv[1:]]
    frames = sorted(RECEIPTS.glob("*.png"))
    if filters:
        frames = [p for p in frames if any(f in p.name.lower() for f in filters)]
    if not frames:
        print("no receipt PNGs matched.")
        return 2
    lst = RECEIPTS / "_demo_list.txt"
    lst.write_text("".join(f"file '{p.name}'\nduration {FPS_FRAME_HOLD}\n" for p in frames)
                   + f"file '{frames[-1].name}'\n", encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-vf", f"scale={WIDTH}:-2", "-pix_fmt", "yuv420p", str(OUT)]
    print(f"{len(frames)} frames -> {OUT}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:])
        return 1
    print(f"done: {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
