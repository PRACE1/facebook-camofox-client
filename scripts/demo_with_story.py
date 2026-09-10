"""Narrated demo cut — title cards (PIL + Arial) + SAPI voiceover, no mic/cam.

Stages receipt frames with spoken explanation. Windows-only (System.Speech).
Output: artifacts\\demo_story.mp4 (gitignored).

Usage (CMD):
  python scripts\\demo_with_story.py              # full narrated cut (~60s)
  python scripts\\demo_with_story.py --no-audio   # cards + frames only
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RECEIPTS = Path("artifacts/receipts")
WORK = Path("artifacts/story")
OUT = Path("artifacts/demo_story.mp4")
W, H = 1280, 720
VF = ("scale=1280:720:force_original_aspect_ratio=decrease,"
      "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30")
CARD_SECONDS = 3.0
FRAME_SECONDS = 1.5
FONT = "C:\\Windows\\Fonts\\arial.ttf"

STAGES = [
    ("Facebook Marketplace automation — end to end",
     "This is our Facebook Marketplace pipeline. Watch a listing get filled, "
     "published, receipted, and health-checked. All automated, all verified.",
     ["__intro_card_only__"]),
    ("Step 1 — form fill (dry run)",
     "First, a dry run. The bot opens the create form, picks the category, "
     "uploads photos, types the title, price, description, and location, then "
     "stops before publishing. Receipt saved.",
     ["form_filled"]),
    ("Step 2 — publish + receipt",
     "Then the real publish. Next, publish, and the listing ID is captured "
     "straight off the seller dashboard. Screenshot receipt, done.",
     ["after_publish", "listing_captured"]),
    ("Step 3 — health watcher",
     "Finally, the watcher. It reads the live dashboard badges, classifies "
     "the listing as active, and only reposts on real takedowns, never on "
     "bans. Thirty nine tests green.",
     ["composer_filled", "after_upload"]),
]


def card(title: str, dest: Path) -> None:
    img = Image.new("RGB", (W, H), (13, 17, 23))
    d = ImageDraw.Draw(img)
    f_big = ImageFont.truetype(FONT, 54)
    f_small = ImageFont.truetype(FONT, 30)
    words, lines, cur = title.split(), [], ""
    for w in words:
        if d.textlength(cur + " " + w, font=f_big) > W - 160:
            lines.append(cur.strip())
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur.strip())
    y = H // 2 - 30 * len(lines)
    for ln in lines:
        d.text((W // 2, y), ln, font=f_big, fill="white", anchor="ma")
        y += 70
    d.text((W // 2, y + 20), "facebook-camofox-client", font=f_small,
           fill=(140, 150, 165), anchor="ma")
    # JPEG, not PNG: the concat demuxer cannot switch codecs mid-stream,
    # so every segment input must be the same format.
    img = img.convert("RGB")
    dest = dest.with_suffix(".jpg")
    img.save(dest, quality=90)
    return dest


def speak(text: str, dest: Path, voice: str = "Microsoft Zira Desktop") -> None:
    ps = ("Add-Type -AssemblyName System.Speech; "
          f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.SelectVoice('{voice}'); "
          f"$s.SetOutputToWaveFile('{dest}'); "
          f"$s.Speak(@'\n{text}\n'@); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:])
        raise SystemExit(1)


def frames_for(filters: list[str]) -> list[Path]:
    frames = sorted(RECEIPTS.glob("*.png"))
    if filters:
        frames = [p for p in frames if any(f in p.name.lower() for f in filters)]
    return frames[:8]


def normalize(frame: Path, idx: int) -> Path:
    """Re-encode through PIL: kills RGBA/16-bit/interlace quirks that
    stall the ffmpeg image pipeline. Returns WORK JPEG path."""
    from PIL import Image

    dest = WORK / f"norm_{idx}.jpg"
    if dest.exists():
        return dest
    Image.open(frame).convert("RGB").save(dest, quality=90)
    return dest


def main() -> int:
    no_audio = "--no-audio" in sys.argv
    WORK.mkdir(parents=True, exist_ok=True)
    seg_videos, seg_audios, seg_durs = [], [], []
    for i, (title, narration, filt) in enumerate(STAGES):
        frames = [normalize(p, n) for n, p in enumerate(frames_for(filt), start=i * 100)]
        card_path = card(title, WORK / f"card_{i}.png")
        dur = CARD_SECONDS + FRAME_SECONDS * len(frames)
        seg_durs.append(dur)
        lst = WORK / f"seg_{i}.txt"
        posix = lambda p: Path(p).resolve().as_posix()
        chunk = "".join(f"file '{posix(p)}'\nduration {FRAME_SECONDS}\n" for p in frames)
        tail = f"file '{posix(frames[-1])}'\n" if frames else ""
        lst.write_text(f"file '{posix(card_path)}'\nduration {CARD_SECONDS}\n"
                       + chunk + tail, encoding="utf-8")
        seg = WORK / f"seg_{i}.mp4"
        if frames:
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-vf", VF,
                 "-fps_mode", "cfr", "-pix_fmt", "yuv420p", str(seg)])
        else:  # card only: concat demuxer emits nothing for a lone still
            run(["ffmpeg", "-y", "-loop", "1", "-i", str(card_path),
                 "-vf", VF,
                 "-t", str(CARD_SECONDS), "-fps_mode", "cfr", "-pix_fmt", "yuv420p", str(seg)])
        seg_videos.append(seg)
        if not no_audio:
            wav = WORK / f"narr_{i}.wav"
            speak(narration, wav)
            padded = WORK / f"narr_{i}_pad.wav"
            run(["ffmpeg", "-y", "-i", str(wav), "-af", f"apad=whole_dur={dur}",
                 "-t", str(dur), str(padded)])
            seg_audios.append(padded)
    vlist = WORK / "vlist.txt"
    vlist.write_text("".join(f"file '{s.resolve().as_posix()}'\n" for s in seg_videos), encoding="utf-8")
    if no_audio or not seg_audios:
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(vlist),
             "-c:v", "libx264", "-fps_mode", "cfr", "-pix_fmt", "yuv420p", str(OUT)])
    else:
        alist = WORK / "alist.txt"
        alist.write_text("".join(f"file '{s.resolve().as_posix()}'\n" for s in seg_audios), encoding="utf-8")
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(vlist),
             "-f", "concat", "-safe", "0", "-i", str(alist),
             "-c:v", "libx264", "-fps_mode", "cfr", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(OUT)])
    print(f"done: {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
