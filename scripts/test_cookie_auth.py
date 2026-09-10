"""Module 1 acceptance: CRM cookie JSON -> logged-in Facebook, no manual login.

Accepts a raw Chrome-extension cookie array OR a storage_state dict.
Exit codes: 0 = authenticated, 1 = expired (CRM must refresh),
2 = browser init failed, 3 = unexpected/usage error.

Run from repo root (CMD):
    python scripts\\test_cookie_auth.py %USERPROFILE%\\fb_cookies.json
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")


async def run_cookie_auth(cookie_path: str) -> int:
    from facebook_camofox_client.domain_camofox.cookie_hydration import (
        AuthExpiredError,
        assert_logged_in,
        extract_cookie_list,
    )
    from facebook_camofox_client.domain_camofox.session_manager import (
        CamofoxSessionManager,
    )

    try:
        data = json.loads(Path(cookie_path).read_text(encoding="utf-8"))
        cookies = extract_cookie_list(data)
        print(f"[cookie-auth] loaded {len(cookies)} raw cookies from {cookie_path}")
    except Exception as exc:
        print(f"[cookie-auth] FAIL reading cookies: {exc}")
        return 3

    manager = CamofoxSessionManager()
    try:
        session = await manager.acquire(account_id="cookie-auth-test", cookies=cookies)
        print(f"[cookie-auth] session acquired: {session.session_id}")
    except Exception as exc:
        print(f"[cookie-auth] FAIL browser init: {exc}")
        return 2

    try:
        page = await session.new_page()
        await page.goto("https://www.facebook.com", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        print(f"[cookie-auth] url={page.url!r}")
        try:
            await assert_logged_in(page)
        except AuthExpiredError as exc:
            print(f"[cookie-auth] FAIL expired: {exc}")
            return 1
        print("[cookie-auth] PASS authenticated without manual login")
        return 0
    except Exception as exc:
        print(f"[cookie-auth] FAIL unexpected: {exc}")
        return 3
    finally:
        await manager.release(session)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts\\test_cookie_auth.py <cookies.json>")
        sys.exit(3)
    sys.exit(asyncio.run(run_cookie_auth(sys.argv[1])))


if __name__ == "__main__":
    main()
