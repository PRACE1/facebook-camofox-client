"""Scan you/selling dashboard — read-only, deletes nothing.

Lists every listing card: ID, title, status hints, href. Saves JSON receipt.

Run from repo root (CMD):
    set CAMOFOX_STORAGE_STATE_LISTEN_GROUP=%USERPROFILE%\\fb_cookies_playwright.json
    python scripts\\scan_selling.py
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager

COOKIE_FILE = Path(os.getenv(
    "CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
    str(Path.home() / "fb_cookies_playwright.json"),
))

EXTRACT_JS = """() => {
  const seen = new Map();
  for (const a of document.querySelectorAll('a[href*="/marketplace/item/"]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/\\/item\\/(\\d+)/);
    if (!m || seen.has(m[1])) continue;
    let el = a, cardText = '';
    for (let i = 0; i < 8 && el; i++) {
      el = el.parentElement;
      if (el && (el.innerText || '').length > (cardText || '').length) cardText = el.innerText;
      if (cardText && cardText.length > 300) break;
    }
    seen.set(m[1], {id: m[1], href, card: (cardText || '').slice(0, 600)});
  }
  return [...seen.values()];
}"""


def summarize(card: str) -> dict:
    low = (card or "").lower()
    lines = [ln.strip() for ln in (card or "").splitlines() if ln.strip()]
    flags = []
    for key in ["being reviewed", "in review", "duplicate", "active", "sold",
                "pending", "rejected", "appeal", "0 clicks", "clicks on listing"]:
        if key in low:
            flags.append(key)
    return {"title": lines[0] if lines else None, "flags": flags}


async def main() -> int:
    if not COOKIE_FILE.exists():
        print(f"Cookie file not found at {COOKIE_FILE}")
        return 2
    mgr = CamofoxSessionManager()
    session = await mgr.acquire("selling-scan", storage_state_path=str(COOKIE_FILE))
    try:
        page = await session.new_page()
        await page.goto("https://www.facebook.com/marketplace/you/selling",
                        wait_until="domcontentloaded")
        try:
            tab = page.get_by_text(re.compile(r"^Your listings$", re.I)).first
            if await tab.count() > 0:
                await tab.click(timeout=5000)
                await page.wait_for_timeout(2000)
        except Exception:
            pass
        try:
            await page.get_by_text(re.compile(r"Your listings", re.I)).first.wait_for(
                state="visible", timeout=20000)
        except Exception:
            pass
        # cards hydrate on scroll — scroll + poll for links up to ~25s
        rows = []
        for _ in range(8):
            try:
                await page.evaluate("window.scrollBy(0, 800)")
            except Exception:
                pass
            await page.wait_for_timeout(2500)
            try:
                rows = await page.evaluate(EXTRACT_JS)
            except Exception:
                rows = []
            if rows:
                break
        if not rows:
            ts_dbg = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                await page.screenshot(
                    path=str(Path("artifacts/receipts") / f"selling_scan_empty_{ts_dbg}.png"),
                    full_page=True)
                (Path("artifacts/receipts") / f"selling_scan_empty_{ts_dbg}.html").write_text(
                    await page.content(), encoding="utf-8")
                print(f"No links after scroll; saved selling_scan_empty_{ts_dbg}.png/.html")
            except Exception:
                pass
        out = []
        for r in rows:
            s = summarize(r.get("card", ""))
            out.append({"id": r["id"], "title": s["title"],
                        "flags": s["flags"], "href": r["href"]})
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = Path("artifacts/receipts") / f"selling_scan_{ts}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Found {len(out)} listing(s). Receipt: {dest}")
        for row in out:
            print(f"- {row['id']} | {row['title']} | flags={','.join(row['flags'])}")
        print("KEEP/DELETE decision is yours — reply with the IDs to delete.")
        return 0
    finally:
        await mgr.release(session)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
