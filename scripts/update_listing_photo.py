"""Swap listing photo: dashboard -> modal -> Edit listing -> add photo -> Update.

LIVE mutation (edits listing 1583545526797714). Verified selectors from
edit_dialog_20260910_063048 dump: file input + role=button "Update".

Run from repo root (CMD):
    set CAMOFOX_STORAGE_STATE_LISTEN_GROUP=%USERPROFILE%\\fb_cookies_playwright.json
    python scripts\\update_listing_photo.py
"""
import asyncio
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
LISTING_ID = os.getenv("EDIT_LISTING_ID", "1583545526797714")
NEW_PHOTO = Path(__file__).parent.parent / "tests" / "fixtures" / "rubbish_galway_02.jpg"
TITLE_RX = re.compile(r"Rubbish Removal & Clearance", re.I)


async def main() -> int:
    if not COOKIE_FILE.exists():
        print(f"Cookie file not found at {COOKIE_FILE}")
        return 2
    if not NEW_PHOTO.exists():
        print(f"Photo not found at {NEW_PHOTO}")
        return 2
    mgr = CamofoxSessionManager()
    session = await mgr.acquire("edit-photo", storage_state_path=str(COOKIE_FILE))
    try:
        page = await session.new_page()
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

        card = page.get_by_text(TITLE_RX).first
        await card.scroll_into_view_if_needed()
        await card.click(timeout=8000)
        await page.wait_for_timeout(3000)
        edit_link = page.get_by_role("link", name=re.compile(r"Edit listing", re.I)).first
        await edit_link.wait_for(state="visible", timeout=15000)
        await edit_link.click(timeout=8000)
        await page.wait_for_timeout(4000)

        print("Uploading new photo...")
        file_input = page.locator('input[type="file"][accept*="image"]').first
        await file_input.set_input_files([str(NEW_PHOTO)])
        try:
            await page.get_by_text(re.compile(r"2\s*/\s*10", re.I)).first.wait_for(
                state="visible", timeout=20000)
            print("  now 2/10 photos.")
        except Exception:
            await page.wait_for_timeout(3000)
            print("  WARNING: 2/10 marker not seen; check screenshot before Update.")
        await dump(f"before_update_{ts}")

        print("Clicking Update...")
        update = page.get_by_role("button", name=re.compile(r"^Update$", re.I)).first
        await update.scroll_into_view_if_needed()
        await update.click(timeout=8000)
        await page.wait_for_timeout(6000)
        await dump(f"after_update_{ts}")
        print(f"Done. Verify at https://www.facebook.com/marketplace/item/{LISTING_ID}/")
        return 0
    finally:
        await mgr.release(session)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
