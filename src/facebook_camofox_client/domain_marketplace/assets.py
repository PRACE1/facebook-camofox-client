"""Replacement asset variation — spintax text + pHash-breaking photo edits.

Spec requires: EXIF strip, 2-4% border crop, +/-1-2% brightness, noise
overlay, else cycle a 3-photo pool. Resizing alone does NOT change pHash.
PIL work runs only if Pillow is installed; otherwise pool-cycling +
spintax still apply and the caller is told pixels were NOT mutated.
"""
from __future__ import annotations

import random
import re
from pathlib import Path

try:
    from PIL import Image, ImageEnhance  # type: ignore

    _PIL_OK = True
except ImportError:  # pragma: no cover
    _PIL_OK = False


def render_spintax(template: str, rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    pattern = re.compile(r"\{([^{}]*)\}")

    def pick(m: re.Match) -> str:
        return rng.choice(m.group(1).split("|"))

    prev, out = None, template
    while prev != out:
        prev, out = out, pattern.sub(pick, out)
    return out


def pick_pool_photo(pool: list[str], exclude: list[str] | None = None) -> str | None:
    exclude = set(exclude or [])
    cands = [p for p in pool if p not in exclude and Path(p).exists()]
    if not cands:
        cands = [p for p in pool if Path(p).exists()]
    return random.choice(cands) if cands else None


def mutate_photo(src: str, dest_dir: str | Path, seed: int | None = None) -> tuple[str, bool]:
    """Return (path_to_use, pixels_mutated). Without Pillow: EXIF-intact
    copy with a unique filename (pool-cycling still required upstream)."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    stem = Path(src).stem
    if not _PIL_OK:  # pragma: no cover
        dest = dest_dir / f"{stem}_poolcopy_{rng.randint(1000, 9999)}{Path(src).suffix}"
        dest.write_bytes(Path(src).read_bytes())
        return str(dest), False
    img = Image.open(src)
    w, h = img.size
    cx, cy = rng.uniform(0.02, 0.04), rng.uniform(0.02, 0.04)
    img = img.crop((int(w * cx), int(h * cy), w - int(w * cx), h - int(h * cy)))
    img = ImageEnhance.Brightness(img).enhance(1.0 + rng.uniform(-0.02, 0.02))
    img = ImageEnhance.Contrast(img).enhance(1.0 + rng.uniform(-0.01, 0.01))
    exif = img.getexif()
    for tag in list(exif.keys()):
        del exif[tag]
    dest = dest_dir / f"{stem}_mut_{rng.randint(1000, 9999)}{Path(src).suffix or '.jpg'}"
    img.save(dest, exif=exif)
    return str(dest), True


def build_replacement(
    title_tpl: str,
    desc_tpl: str,
    photo_pool: list[str],
    dest_dir: str | Path,
    used_photos: list[str] | None = None,
    seed: int | None = None,
) -> dict:
    rng = random.Random(seed)
    src = pick_pool_photo(photo_pool, exclude=used_photos)
    if src is None:
        raise ValueError("photo pool exhausted: no existing file to use")
    mutated, pixels = mutate_photo(src, dest_dir, seed=seed)
    return {
        "title": render_spintax(title_tpl, rng),
        "description": render_spintax(desc_tpl, rng),
        "image_path": mutated,
        "source_photo": src,
        "pixels_mutated": pixels,
    }
