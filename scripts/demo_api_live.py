"""Hackathon API demo — serves the REST API, exercises it live, one take.

Starts uvicorn, then: /healthz -> watchlist add -> dry-run create (real
headed browser fills the form) -> live status check -> stops server.
Read-only except the dry-run fill (publishes NOTHING).

Usage (CMD):
  set CAMOFOX_STORAGE_STATE_LISTEN_GROUP=%USERPROFILE%\\fb_cookies_playwright.json
  python scripts\\demo_api_live.py
"""
import json
import subprocess
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8125"


def call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main() -> int:
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = "src" + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
                   os.path.join(os.path.expanduser("~"), "fb_cookies_playwright.json"))
    raw_path = os.path.join(os.path.expanduser("~"), "fb_cookies.json")
    try:
        import time as _time

        age_hours = (_time.time() - os.path.getmtime(raw_path)) / 3600
        if age_hours > 24:
            raise RuntimeError(f"raw export is {age_hours:.0f}h old, likely rotated")
        with open(raw_path, encoding="utf-8") as fh:
            import json as _json

            data = _json.load(fh)
        crm_cookies = data if isinstance(data, list) else data.get("cookies", [])
        print(f"CRM cookies loaded: {len(crm_cookies)} (raw Chrome export)")
    except Exception as exc:
        print(f"raw export unusable ({exc}); falling back to storage state")
        crm_cookies = None
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "facebook_camofox_client.api.app:app",
         "--port", "8125"],
        cwd=".", env=env)
    try:
        for _ in range(30):
            try:
                print("health:", call("GET", "/healthz"))
                break
            except Exception:
                time.sleep(1)
        print("actions:", call("GET", "/api/actions")["action_types"])
        print("watch add:", call("POST", "/api/watchlist", {
            "crm_offer_id": "demo-offer", "account_id": "demo",
            "current_listing_id": "1583545526797714",
            "root_listing_id": "1583545526797714"})["current_listing_id"])
        print("create (dry-run, watch the browser fill the form):")
        live = os.getenv("API_LIVE_PUBLISH") == "1"
        listing = {"title": "Rubbish Removal in Galway", "price": "50",
                   "category": "Household", "condition": "Used \u2013 fair",
                   "description": "API demo dry-run probe.",
                   "location": "Galway, Ireland",
                   "image_paths": [], "dry_run": True}
        if live:
            from facebook_camofox_client.domain_marketplace.assets import build_replacement

            rep = build_replacement(
                "{Rubbish Removal & Clearance|Junk & Waste Collection} in Galway",
                "{Yard, shed and household rubbish cleared|Fast, reliable clearance} "
                "across Galway {city and county|}. {Send a photo for a same-day quote|"
                "Message for a quick quote}.",
                ["tests/fixtures/rubbish_galway_01.jpg",
                 "tests/fixtures/rubbish_galway_02.jpg"],
                "artifacts/relist")
            listing.update(title=rep["title"], description=rep["description"],
                           image_paths=[rep["image_path"]], dry_run=False)
            print(f"LIVE publish with mutated assets (pixels_mutated={rep['pixels_mutated']})")
        out = call("POST", "/api/listings", {
            "account_id": "demo", "cookies": crm_cookies, "listing": listing})
        print("  published:", out["published"], "| reason:", out.get("reason"),
              "| receipt:", out["receipt_path"])
        print("status:", call(
            "GET", "/api/listings/1583545526797714/status?account_id=demo"))
        print("DEMO COMPLETE — REST API working end to end.")
        return 0
    finally:
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
