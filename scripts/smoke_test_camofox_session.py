"""
Runtime smoke test — OPT-IN ONLY.

This is NOT part of the normal test suite. It requires:
  - camofox installed and licensed
  - A real fb_cookies.json file
  - (Optional) A proxy config

Run manually:
  python scripts/smoke_test_camofox_session.py \
    --cookies /path/to/fb_cookies.json \
    --proxy "http://user:pass@host:port" \
    --group-id "123456789"

Exit codes:
  0 = session acquired, auth passed, closed cleanly
  1 = auth state not 'authenticated' (cookies stale / checkpoint hit)
  2 = browser failed to initialize
  3 = unexpected exception
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, UTC


async def run_smoke(cookies_path: str, proxy_url: str | None, group_id: str) -> int:
    print(f"[smoke] starting at {datetime.now(UTC).isoformat()}")

    # --- 1. Import boundary check ---
    try:
        from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
        from facebook_camofox_client.domain_accounts.auth_guard import AuthGuard, AuthState
        print("[smoke] imports ok")
    except ImportError as e:
        print(f"[smoke] FAIL import: {e}")
        return 3

    # --- 2. Load cookies ---
    try:
        with open(cookies_path, encoding="utf-8") as f:
            cookies = json.load(f)
        print(f"[smoke] cookies loaded: {len(cookies)} entries from {cookies_path}")
    except Exception as e:
        print(f"[smoke] FAIL loading cookies: {e}")
        return 3

    # --- 3. Acquire session (real AsyncCamoufox) ---
    proxy_config = {"server": proxy_url} if proxy_url else None
    manager = CamofoxSessionManager()

    try:
        session = await manager.acquire(
            account_id="smoke-test-account",
            proxy_config=proxy_config,
        )
        print(f"[smoke] session acquired: {session.session_id}")
    except Exception as e:
        print(f"[smoke] FAIL browser init: {e}")
        return 2

    try:
        # --- 4. Inject cookies into session context ---
        # Camofox exposes context via session.browser
        try:
            await session.browser.add_cookies(cookies)
            print(f"[smoke] cookies injected into browser context")
        except Exception as e:
            print(f"[smoke] WARN could not inject cookies directly: {e}")

        # --- 5. Open the target surface ---
        await session.open_surface("facebook_group", {"group_id": group_id})
        print(f"[smoke] surface opened: facebook_group/{group_id}")

        # --- 6. Get page state for auth_guard ---
        page_title, page_url = await session.get_current_page_state()
        print(f"[smoke] page_title={page_title!r}  page_url={page_url!r}")

        # --- 7. Auth guard validates DOM state ---
        guard = AuthGuard()
        result = await guard.validate(page_title=page_title, page_url=page_url)
        print(f"[smoke] auth_guard state: {result.state}")

        if result.state != AuthState.authenticated:
            print(f"[smoke] FAIL not authenticated — requires_action={result.requires_action}")
            return 1

        print("[smoke] PASS auth_guard returned authenticated")

    except Exception as e:
        print(f"[smoke] FAIL unexpected: {e}")
        return 3
    finally:
        # --- 8. Close cleanly ---
        await manager.release(session.session_id)
        print(f"[smoke] session released cleanly")

    print(f"[smoke] DONE at {datetime.now(UTC).isoformat()} — browser initialized, auth passed, closed cleanly")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Opt-in runtime smoke test for CamofoxSessionManager. DO NOT run in CI."
    )
    parser.add_argument("--cookies", required=True, help="Path to fb_cookies.json")
    parser.add_argument("--proxy", default=None, help="Proxy URL e.g. http://user:pass@host:port")
    parser.add_argument("--group-id", default="123456789", help="Facebook group ID to open")
    args = parser.parse_args()

    exit_code = asyncio.run(run_smoke(
        cookies_path=args.cookies,
        proxy_url=args.proxy,
        group_id=args.group_id,
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
