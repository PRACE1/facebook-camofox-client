"""Live dry-run of MarketplaceCreateAction — fills form, NO publish.

Uses the real CamofoxSessionManager + production action with dry_run=True.
Proves session -> driver -> receipt path without creating a listing.

Run from repo root (CMD):
    set CAMOFOX_STORAGE_STATE_LISTEN_GROUP=%USERPROFILE%\\fb_cookies_playwright.json
    python scripts\\run_marketplace_create_dryrun.py
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_marketplace.create import MarketplaceCreateAction
from facebook_camofox_client.domain_marketplace.receipts import ReceiptStore

COOKIE_FILE = Path(os.getenv(
    "CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
    str(Path.home() / "fb_cookies_playwright.json"),
))
ACCOUNT_ID = os.getenv("MARKETPLACE_ACCOUNT_ID", "marketplace-dryrun")


async def main() -> int:
    if not COOKIE_FILE.exists():
        print(f"Cookie file not found at {COOKIE_FILE}")
        return 2
    print(f"Using storage state: {COOKIE_FILE}")

    manager = CamofoxSessionManager()
    # Wrap acquire so the action uses our explicit cookie file regardless of env.
    real_acquire = manager.acquire

    async def acquire(account_id, **kwargs):
        kwargs.setdefault("storage_state_path", str(COOKIE_FILE))
        return await real_acquire(account_id, **kwargs)

    manager.acquire = acquire  # type: ignore[method-assign]

    emitter = InMemoryEventEmitter()
    receipts = ReceiptStore()
    action = MarketplaceCreateAction(manager, emitter, receipts)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    envelope = ActionEnvelope(
        action_id=f"dryrun-{ts}",
        action_type=MarketplaceCreateAction.ACTION_TYPE,
        account_id=ACCOUNT_ID,
        input={
            "title": "Rubbish Removal in Galway",
            "price": "50",
            "category": "Household",
            "condition": "Used \u2013 fair",
            "description": "Fast and reliable rubbish clearance across Galway. Message for a quick quote.",
            "location": "Galway, Ireland",
            "image_paths": [
                str(Path("tests/fixtures/groups_search/group_305056891435827_20260817T204349.png")),
            ],
            "dry_run": True,
        },
        idempotency_key=f"dryrun-{ts}",
    )
    out = await action.execute(envelope)
    print(f"published={out.published} listing_id={out.listing_id} url={out.listing_url}")
    for e in emitter.events:
        print(f"event: {e.event_type} {e.payload}")
    print("DRY-RUN OK — form filled, receipts saved, nothing published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
