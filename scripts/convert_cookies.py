"""Convert a raw browser-extension cookie export into Playwright's
storage_state JSON format.

Input:  raw list of cookie objects (e.g. exported via Cookie-Editor)
Output: {"cookies": [...], "origins": []} with Playwright-compatible
        field names and values.

Run from the repo root:
    python scripts\\convert_cookies.py
"""
import json
from pathlib import Path

SOURCE = Path(r"C:\Users\R5 5600 GT\fb_cookies.json")
DEST = Path(r"C:\Users\R5 5600 GT\fb_cookies_playwright.json")

SAME_SITE_MAP = {
    "lax": "Lax",
    "strict": "Strict",
    "no_restriction": "None",
    "unspecified": "Lax",  # Playwright has no "unspecified"; Lax is the safe default
}


def convert_cookie(raw: dict) -> dict:
    same_site_raw = (raw.get("sameSite") or "lax").lower()
    same_site = SAME_SITE_MAP.get(same_site_raw, "Lax")

    cookie = {
        "name": raw["name"],
        "value": raw["value"],
        "domain": raw["domain"],
        "path": raw.get("path", "/"),
        "secure": bool(raw.get("secure", False)),
        "httpOnly": bool(raw.get("httpOnly", False)),
        "sameSite": same_site,
    }

    # session cookies (no expiry) must be omitted or Playwright treats
    # them as persistent; only include expires if the source had a real one
    if not raw.get("session", False) and raw.get("expirationDate"):
        cookie["expires"] = raw["expirationDate"]

    return cookie


def main():
    raw_cookies = json.loads(SOURCE.read_text(encoding="utf-8"))
    print(f"Loaded {len(raw_cookies)} raw cookies from {SOURCE}")

    converted = [convert_cookie(c) for c in raw_cookies]

    storage_state = {
        "cookies": converted,
        "origins": [],
    }

    DEST.write_text(json.dumps(storage_state, indent=2), encoding="utf-8")
    print(f"Wrote Playwright storage_state to {DEST}")

    names = [c["name"] for c in converted]
    print(f"Converted cookie names: {names}")
    for required in ("c_user", "xs"):
        status = "present" if required in names else "MISSING"
        print(f"  {required}: {status}")


if __name__ == "__main__":
    main()
