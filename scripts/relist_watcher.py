"""Relist watcher daemon — poll dashboard, auto-repost on takedown only.

Separate process from the group listener (different cadence: 4-6h + jitter,
12min first check). One cycle per run; schedule via Task Scheduler/cron.
Never reposts on fatal states; lineage receipts per generation.

Usage (CMD): python scripts\\relist_watcher.py state\\watchlist.json
Watchlist JSON: [{"crm_offer_id":..,"account_id":..,"current_listing_id":..,
  "root_listing_id":..,"parent_listing_id":..,"generation":0 status?...}]
"""
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_marketplace.health import check_dashboard_health
from facebook_camofox_client.domain_marketplace.relist import (
    ListingHealthStatus,
    MonitoredListing,
    RelistPolicyConfig,
    evaluate_relist_trigger,
)

COOKIE_FILE = Path(os.getenv(
    "CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
    str(Path.home() / "fb_cookies_playwright.json"),
))


async def run_cycle(watchlist_path: str, config: RelistPolicyConfig) -> int:
    items = json.loads(Path(watchlist_path).read_text(encoding="utf-8"))
    manager = CamofoxSessionManager()
    real_acquire = manager.acquire

    async def acquire(account_id, **kwargs):
        kwargs.setdefault("storage_state_path", str(COOKIE_FILE))
        return await real_acquire(account_id, **kwargs)

    manager.acquire = acquire  # type: ignore[method-assign]
    emitter = InMemoryEventEmitter()
    fatal = False
    for raw in items:
        listing = MonitoredListing(**raw)
        session = await manager.acquire(listing.account_id)
        try:
            page = await session.new_page()
            status, card = await check_dashboard_health(page, listing.current_listing_id)
        finally:
            await manager.release(session)
        listing.status = status
        listing.last_checked_at = datetime.now(timezone.utc)
        decision = evaluate_relist_trigger(listing, status, config)
        print(f"[{listing.current_listing_id}] {status.value} -> {decision.reason}")
        await emitter.emit(
            "marketplace.health_checked",
            {"listing_id": listing.current_listing_id, "status": status.value,
             "repost": decision.should_repost, "generation": listing.generation},
            dedupe_key=f"{listing.current_listing_id}-{listing.generation}",
        )
        if decision.fatal_error:
            print(f"  FATAL: locking {listing.current_listing_id}, stopping watcher.")
            fatal = True
            break
        if decision.should_repost:
            print(f"  cooldown {decision.cooldown_seconds}s, then repost as gen {decision.next_generation} "
                  f"(wire to MarketplaceCreateAction with mutated assets).")
    return 1 if fatal else 0


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts\\relist_watcher.py <watchlist.json>")
        sys.exit(2)
    jitter = random.randint(60, 300)
    print(f"jitter {jitter}s (skipped in single-cycle mode)")
    sys.exit(asyncio.run(run_cycle(sys.argv[1], RelistPolicyConfig())))


if __name__ == "__main__":
    main()
