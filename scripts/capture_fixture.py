"""Capture a real Facebook group page as an HTML + screenshot fixture.

This does NOT extract posts yet — it just saves what the page actually
looks like so we can build [role="article"] selectors against real markup
instead of guessing.

Run from the repo root:
    python scripts\\capture_fixture.py
"""
import asyncio
import sys
import json
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager

COOKIES_FILE = r"C:\Users\R5 5600 GT\fb_cookies.json"
GROUP_ID = "305056891435827"
OUT_DIR = Path("tests/fixtures/groups_search")


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mgr = CamofoxSessionManager()
    session = await mgr.acquire(
        account_id="fixture-capture",
        storage_state_path=COOKIES_FILE,
    )

    try:
        page = await session.open_surface(
            "facebook_group",
            {"group_id": GROUP_ID},
        )

        # bounded wait for feed content to render
        await page.wait_for_timeout(3000)

        # more scroll iterations with longer pauses, so Facebook fully
        # hydrates each post's Relay data instead of leaving lazy stubs
        for _ in range(8):
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(1800)

        html = await page.content()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        html_path = OUT_DIR / f"group_{GROUP_ID}_{timestamp}.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"Saved HTML: {html_path} ({len(html)} chars)")

        screenshot_path = OUT_DIR / f"group_{GROUP_ID}_{timestamp}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Saved screenshot: {screenshot_path}")

        # quick sanity check: how many role="article" elements are present?
        count = await page.locator('[role="article"]').count()
        print(f'[role="article"] elements found: {count}')

    finally:
        await mgr.release(session)


if __name__ == "__main__":
    asyncio.run(main())
