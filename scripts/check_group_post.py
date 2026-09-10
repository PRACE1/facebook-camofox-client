"""Check whether the group post landed — read-only."""
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager

COOKIE_FILE = Path(os.getenv(
    "CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
    str(Path.home() / "fb_cookies_playwright.json"),
))
GROUP_ID = "305056891435827"
NEEDLE = re.compile(r"clearing space.*rubbish removal", re.I | re.S)


async def main() -> int:
    mgr = CamofoxSessionManager()
    session = await mgr.acquire("post-check", storage_state_path=str(COOKIE_FILE))
    try:
        page = await session.new_page()
        await page.goto(f"https://www.facebook.com/groups/{GROUP_ID}?sorting_setting=CHRONOLOGICAL",
                        wait_until="domcontentloaded")
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, 900)")
            await page.wait_for_timeout(2500)
            try:
                body = await page.locator("body").inner_text(timeout=5000)
            except Exception:
                body = ""
            if NEEDLE.search(body or ""):
                print("FOUND: post text is live in the group feed.")
                return 0
        print("NOT FOUND in feed (yet): likely in admin approval queue or still posting.")
        print("Check: group Discussion sorted Newest, or your profile pending posts.")
        return 1
    finally:
        await mgr.release(session)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
