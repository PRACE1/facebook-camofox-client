"""Discover the Edit-listing photo flow — saves dumps, changes NOTHING.

Opens the item page, clicks Edit, screenshots the edit dialog for ground
truth, then closes WITHOUT saving. Read-only by design.

Run from repo root (CMD):
    set CAMOFOX_STORAGE_STATE_LISTEN_GROUP=%USERPROFILE%\\fb_cookies_playwright.json
    python scripts\\discover_edit_photo.py 1583545526797714
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager

COOKIE_FILE = Path(os.getenv(
    "CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
    str(Path.home() / "fb_cookies_playwright.json"),
))


async def main(listing_id: str) -> int:
    if not COOKIE_FILE.exists():
        print(f"Cookie file not found at {COOKIE_FILE}")
        return 2
    mgr = CamofoxSessionManager()
    session = await mgr.acquire("edit-discover", storage_state_path=str(COOKIE_FILE))
    try:
        page = await session.new_page()
        # Proven path: dashboard card -> "Your listing" modal -> "Edit listing".
        # (Item-page Edit pill mis-clicks; modal path opened reliably before.)
        await page.goto("https://www.facebook.com/marketplace/you/selling",
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = Path("artifacts/receipts")
        dest.mkdir(parents=True, exist_ok=True)

        async def dump(name):
            await page.screenshot(path=str(dest / f"{name}.png"), full_page=True)
            (dest / f"{name}.html").write_text(await page.content(), encoding="utf-8")
            print(f"saved {name}.png/.html")

        import re
        card = page.get_by_text(re.compile(r"Rubbish Removal & Clearance", re.I)).first
        try:
            await card.scroll_into_view_if_needed()
            await card.click(timeout=8000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"card click failed ({e})")
            await dump(f"edit_cards_{ts}")
            return 1
        await dump(f"edit_modal_{ts}")
        edit_btn = page.get_by_role(
            "link", name=re.compile(r"Edit listing", re.I)).first
        try:
            if await edit_btn.count() == 0 or not await edit_btn.is_visible():
                print("Edit listing button not in modal — inspect edit_modal dump.")
                return 1
            await edit_btn.click(timeout=8000)
            await page.wait_for_timeout(4000)
        except Exception as e:
            print(f"Edit listing click failed ({e})")
            return 1
        await dump(f"edit_dialog_{ts}")
        print("Discovery only — nothing changed. Send edit_dialog dump state.")
        return 0
    finally:
        await mgr.release(session)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts\\discover_edit_photo.py <listing_id>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
