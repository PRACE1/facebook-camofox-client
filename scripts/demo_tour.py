"""Hackathon demo tour — inbound feed scroll + outbound form fill, one take.

Opens the group Discussion, slow-scrolls real posts, then fills a
marketplace listing (dry-run: nothing published). Hands-free under
scripts/lead_in.py + Cap.

Usage (CMD):
  python scripts\\lead_in.py 15 -- python scripts\\demo_tour.py
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
GROUP_ID = os.getenv("GROUP_POST_GROUP_ID", "305056891435827")
SCROLLS, SCROLL_PAUSE = 10, 3.0


async def main() -> int:
    mgr = CamofoxSessionManager()
    session = await mgr.acquire("demo-tour", storage_state_path=str(COOKIE_FILE))
    try:
        feed = await session.new_page()
        await feed.goto(f"https://www.facebook.com/groups/{GROUP_ID}?sorting_setting=CHRONOLOGICAL",
                        wait_until="domcontentloaded")
        await feed.wait_for_timeout(4000)
        for i in range(SCROLLS):
            await feed.evaluate("window.scrollBy(0, 700)")
            await feed.wait_for_timeout(int(SCROLL_PAUSE * 1000))
        print(f"feed scrolled ({SCROLLS} steps)")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        action = MarketplaceCreateAction(session_manager=_Fixed(session, mgr),
                                         event_emitter=InMemoryEventEmitter(),
                                         receipt_store=ReceiptStore())
        env = ActionEnvelope(
            action_id=f"demotour-{ts}", action_type=MarketplaceCreateAction.ACTION_TYPE,
            account_id="demo-tour",
            input={"title": "Rubbish Removal in Galway", "price": "50",
                   "category": "Household", "condition": "Used \u2013 fair",
                   "description": "Fast and reliable rubbish clearance across Galway.",
                   "location": "Galway, Ireland", "image_paths": [],
                   "dry_run": True},
            idempotency_key=f"demotour-{ts}",
        )
        out = await action.execute(env)
        print(f"form filled, published={out.published} (dry-run)")
        return 0
    finally:
        await mgr.release(session)


class _Fixed:
    """Reuse the live session instead of acquiring a second browser."""

    def __init__(self, session, mgr):
        self._session, self._mgr = session, mgr

    async def acquire(self, account_id, **kwargs):
        return self._session

    async def release(self, session):
        pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
