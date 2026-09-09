"""Open Camoufox, let you log into Facebook manually, then save storage_state.

Keeps the browser open even if navigation is slow/times out so you can
finish login, then writes a fresh Playwright storage_state.

Run from the repo root:
    python scripts\\interactive_login.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager

COOKIES_FILE = Path(r"C:\Users\R5 5600 GT\fb_cookies_playwright.json")
GROUP_ID = "305056891435827"
GOTO_TIMEOUT_MS = 120_000


async def _auth_flags(page) -> dict[str, bool]:
    title = (await page.title()).lower()
    url = page.url.lower()
    login_modal = await page.locator("text=See more on Facebook").count()
    login_form = await page.locator('input[name="email"]').count()
    checkpoint = await page.locator("text=checkpoint").count()
    return {
        "login_in_url_or_title": ("login" in url) or ("log in" in title),
        "see_more_modal": login_modal > 0,
        "login_email_field": login_form > 0,
        "checkpoint": checkpoint > 0,
    }


async def _safe_goto(page, url: str) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    except Exception as exc:
        print(f"Navigation warning ({url}): {exc}")
        print("Browser stays open — continue in the Camoufox window.")


async def main() -> None:
    mgr = CamofoxSessionManager()
    storage = str(COOKIES_FILE) if COOKIES_FILE.exists() else None
    session = await mgr.acquire(
        account_id="listen-group",
        storage_state_path=storage,
    )

    try:
        page = await session.context.new_page()
        page.set_default_timeout(GOTO_TIMEOUT_MS)

        # Land on facebook.com first (often more reliable than deep-linking a group)
        await _safe_goto(page, "https://www.facebook.com/")
        await page.wait_for_timeout(2000)
        await _safe_goto(page, f"https://web.facebook.com/groups/{GROUP_ID}")
        await page.wait_for_timeout(2000)

        try:
            flags = await _auth_flags(page)
            print("Browser is open. Current auth flags:")
            for key, value in flags.items():
                print(f"  {key}: {value}")
        except Exception as exc:
            print(f"Could not read auth flags yet: {exc}")

        print()
        print("In the Camoufox window:")
        print("  1. Log into Facebook (complete any checkpoint / 2FA)")
        print("  2. Confirm you can see the group feed (no login wall)")
        print("  3. Come back HERE and press Enter to save the session")
        print()
        print("Do NOT close the browser yourself — wait for Enter.")
        await asyncio.to_thread(input, "Press Enter after you are fully logged in... ")

        try:
            await page.reload(wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
            await page.wait_for_timeout(2500)
            flags = await _auth_flags(page)
            print("\nAuth flags after login:")
            for key, value in flags.items():
                print(f"  {key}: {value}")
            bad = any(flags.values())
        except Exception as exc:
            print(f"\nCould not re-check auth flags: {exc}")
            bad = True

        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        await session.context.storage_state(path=str(COOKIES_FILE))
        print(f"\nSaved storage_state -> {COOKIES_FILE}")

        if bad:
            print(
                "WARNING: login indicators may still be present. "
                "If the feed looked logged-in, re-run diagnose_auth anyway."
            )
        else:
            print("Looks authenticated. Next: python scripts\\diagnose_auth.py")
    finally:
        await mgr.release(session)


if __name__ == "__main__":
    asyncio.run(main())
