"""Live status check for one listing — read-only, creates nothing.

Run from repo root (CMD):
    set CAMOFOX_STORAGE_STATE_LISTEN_GROUP=%USERPROFILE%\\fb_cookies_playwright.json
    python scripts\\run_marketplace_status.py 38629807913299080
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_marketplace.status import MarketplaceStatusAction

COOKIE_FILE = Path(os.getenv(
    "CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
    str(Path.home() / "fb_cookies_playwright.json"),
))
ACCOUNT_ID = os.getenv("MARKETPLACE_ACCOUNT_ID", "marketplace-status")


async def main(listing_id: str) -> int:
    if not COOKIE_FILE.exists():
        print(f"Cookie file not found at {COOKIE_FILE}")
        return 2
    manager = CamofoxSessionManager()
    real_acquire = manager.acquire

    async def acquire(account_id, **kwargs):
        kwargs.setdefault("storage_state_path", str(COOKIE_FILE))
        return await real_acquire(account_id, **kwargs)

    manager.acquire = acquire  # type: ignore[method-assign]
    emitter = InMemoryEventEmitter()
    action = MarketplaceStatusAction(manager, emitter)
    env = ActionEnvelope(
        action_id=f"status-{listing_id}", action_type=MarketplaceStatusAction.ACTION_TYPE,
        account_id=ACCOUNT_ID, input={"listing_id": listing_id},
        idempotency_key=f"status-{listing_id}",
    )
    out = await action.execute(env)
    print(f"listing_id={out.listing_id} status={out.status} title={out.title!r} url={out.listing_url}")
    for e in emitter.events:
        print(f"event: {e.event_type} {e.payload}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts\\run_marketplace_status.py <listing_id>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
