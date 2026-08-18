"""Diagnostic: confirm whether cookies from storage_state actually
attached to the live browser context, and check for Facebook checkpoint
indicators on the page.

Run from the repo root:
    python scripts\\diagnose_auth.py
"""
import asyncio
import sys

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager

COOKIES_FILE = r"C:\Users\R5 5600 GT\fb_cookies_playwright.json"
GROUP_ID = "305056891435827"


async def main():
    mgr = CamofoxSessionManager()
    session = await mgr.acquire(
        account_id="diag",
        storage_state_path=COOKIES_FILE,
    )

    try:
        # Check what the browser context actually has loaded
        context_cookies = await session.context.cookies()
        print(f"Cookies actually in browser context: {len(context_cookies)}")
        for c in context_cookies:
            print(f"  - {c['name']} (domain={c['domain']})")

        has_c_user = any(c["name"] == "c_user" for c in context_cookies)
        has_xs = any(c["name"] == "xs" for c in context_cookies)
        print(f"\nc_user present in context: {has_c_user}")
        print(f"xs present in context: {has_xs}")

        # Now navigate and check the actual page state
        page = await session.open_surface(
            "facebook_group",
            {"group_id": GROUP_ID},
        )
        await page.wait_for_timeout(2000)

        title = await page.title()
        url = page.url
        print(f"\nPage title: {title}")
        print(f"Page URL: {url}")

        # Check for login modal / checkpoint indicators
        login_modal = await page.locator("text=See more on Facebook").count()
        checkpoint = await page.locator("text=checkpoint").count()
        login_form = await page.locator('input[name="email"]').count()

        print(f"\n'See more on Facebook' modal present: {login_modal > 0}")
        print(f"'checkpoint' text present: {checkpoint > 0}")
        print(f"Login email field present: {login_form > 0}")

    finally:
        await mgr.release(session)


if __name__ == "__main__":
    asyncio.run(main())
