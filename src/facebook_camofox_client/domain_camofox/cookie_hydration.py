"""CRM cookie hydration — inject raw Chrome-export cookies into a context.

Unlike scripts/convert_cookies.py (one-shot file conversion), this works
in-process: normalize Chrome-extension formats, add_cookies, verify login.
No intermediate storage_state file needed.
"""
from __future__ import annotations

from typing import Any


class AuthExpiredError(RuntimeError):
    """Raised when facebook.com redirects to /login after hydration —
    the CRM must refresh the session token."""


_SAME_SITE_MAP = {
    "lax": "Lax",
    "strict": "Strict",
    "no_restriction": "None",
    "none": "None",
    "unspecified": "Lax",  # Playwright has no "unspecified"; Lax is safe
}


def normalize_chrome_cookie(raw: dict) -> dict:
    same_site = _SAME_SITE_MAP.get(str(raw.get("sameSite") or "lax").lower(), "Lax")
    secure = bool(raw.get("secure", False))
    if same_site == "None" and not secure:
        # Browsers reject SameSite=None without Secure — downgrade, don't drop.
        same_site = "Lax"
    cookie: dict[str, Any] = {
        "name": raw["name"],
        "value": raw["value"],
        "domain": raw.get("domain") or ".facebook.com",
        "path": raw.get("path", "/"),
        "secure": secure,
        "httpOnly": bool(raw.get("httpOnly", False)),
        "sameSite": same_site,
    }
    if not raw.get("session", False) and raw.get("expirationDate"):
        try:
            cookie["expires"] = int(float(raw["expirationDate"]))
        except (TypeError, ValueError):
            pass
    return cookie


def normalize_chrome_cookies(raw_list: list[dict]) -> list[dict]:
    out = []
    for raw in raw_list:
        try:
            if raw.get("name") and raw.get("value") is not None:
                out.append(normalize_chrome_cookie(raw))
        except (KeyError, TypeError, AttributeError):
            continue
    return out


def extract_cookie_list(data: Any) -> list[dict]:
    """Accept a raw Chrome array OR a storage_state dict {"cookies": [...]};
    anything else raises ValueError (fail loud, never guess)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("cookies"), list):
        return data["cookies"]
    raise ValueError("cookie JSON must be a list or a storage_state dict with 'cookies'")


async def hydrate_context(context, cookies_data: list[dict]) -> list[dict]:
    """Normalize + add_cookies. Returns what was injected (for receipts)."""
    formatted = normalize_chrome_cookies(cookies_data)
    if not formatted:
        raise ValueError("no usable cookies after normalization")
    await context.add_cookies(formatted)
    return formatted


def is_logged_in(url: str, title: str) -> bool:
    # Same guard as every action's auth check: login redirect = expired.
    return "login" not in (url or "").lower()


async def assert_logged_in(page) -> None:
    """Positive proof required: a logged-in marker must exist. URL-only
    checks false-pass (anon facebook.com keeps a clean URL with _rdc dance
    and a bare 'Facebook' title)."""
    url = page.url
    if "login" in (url or "").lower():
        raise AuthExpiredError(f"redirected to login ({url!r}) — CRM must refresh cookies")
    markers = 0
    for sel in ('a[href*="/marketplace/"]', '[aria-label="Your profile"]',
                'div[role="textbox"]'):
        try:
            if await page.locator(sel).count() > 0:
                markers += 1
        except Exception:
            continue
    if markers == 0:
        try:
            title = await page.title()
        except Exception:
            title = ""
        raise AuthExpiredError(
            f"no logged-in markers at {url!r} (title {title!r}) — cookies stale")
