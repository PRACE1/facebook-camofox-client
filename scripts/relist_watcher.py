"""Relist watcher daemon — poll dashboard, auto-repost on takedown only.

Separate process from the group listener (different cadence: 4-6h + jitter,
12min first check). One cycle per run; schedule via Task Scheduler/cron.
Never reposts on fatal states; lineage receipts per generation.

Repost leg is gated: RELIST_LIVE=1 actually publishes via
MarketplaceCreateAction; otherwise the cycle prints what it WOULD do.
Cooldowns enforced via next_eligible_at persisted in the state file.

Usage (CMD): python scripts\\relist_watcher.py state\\watchlist.json
Watchlist JSON entries: MonitoredListing fields + title_tpl/desc_tpl/
photo_pool/price/category/location (see domain_marketplace/relist.py).
"""
import asyncio
import json
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_marketplace.assets import build_replacement
from facebook_camofox_client.domain_marketplace.create import MarketplaceCreateAction
from facebook_camofox_client.domain_marketplace.health import check_dashboard_health
from facebook_camofox_client.domain_marketplace.receipts import ReceiptStore
from facebook_camofox_client.domain_marketplace.relist import (
    ListingHealthStatus,
    MonitoredListing,
    RelistPolicyConfig,
    evaluate_relist_trigger,
    is_due,
)

COOKIE_FILE = Path(os.getenv(
    "CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
    str(Path.home() / "fb_cookies_playwright.json"),
))
RELIST_LIVE = os.getenv("RELIST_LIVE") == "1"


async def run_cycle(watchlist_path: str, config: RelistPolicyConfig) -> int:
    state_file = Path(watchlist_path)
    items = json.loads(state_file.read_text(encoding="utf-8"))
    manager = CamofoxSessionManager()
    real_acquire = manager.acquire

    async def acquire(account_id, **kwargs):
        kwargs.setdefault("storage_state_path", str(COOKIE_FILE))
        return await real_acquire(account_id, **kwargs)

    manager.acquire = acquire  # type: ignore[method-assign]
    emitter = InMemoryEventEmitter()
    fatal = False
    out_items: list[dict] = []
    for raw in items:
        listing = MonitoredListing(**raw)
        session = await manager.acquire(listing.account_id)
        try:
            page = await session.new_page()
            status, card, clicks = await check_dashboard_health(
                page, listing.current_listing_id, getattr(listing, "title", ""))
        finally:
            await manager.release(session)
        listing.status = status
        listing.last_checked_at = datetime.now(UTC)
        decision = evaluate_relist_trigger(listing, status, config)
        print(f"[{listing.current_listing_id}] {status.value} -> {decision.reason}")
        await emitter.emit(
            "marketplace.health_checked",
            {"listing_id": listing.current_listing_id, "status": status.value,
             "repost": decision.should_repost, "generation": listing.generation},
            dedupe_key=f"{listing.current_listing_id}-{listing.generation}",
        )
        try:
            from facebook_camofox_client.domain_marketplace.webhooks import (
                alert_raised_event,
                dispatch,
                health_checked_event,
                superseded_event,
            )
            await dispatch(health_checked_event(
                listing_id=listing.current_listing_id, status=status.value,
                clicks=clicks))
        except Exception:
            pass
        if decision.fatal_error:
            print(f"  FATAL: locking {listing.current_listing_id}, stopping watcher.")
            try:
                await dispatch(alert_raised_event(
                    listing_id=listing.current_listing_id,
                    root_listing_id=listing.root_listing_id,
                    offer_id=listing.crm_offer_id,
                    alert_type=status.value,
                    message=f"Watcher halted: {decision.reason}",
                    last_status=status.value))
            except Exception:
                pass
            out_items.append(listing.model_dump(mode="json"))
            fatal = True
            break
        if not decision.should_repost and "max repost" in decision.reason:
            try:
                await dispatch(alert_raised_event(
                    listing_id=listing.current_listing_id,
                    root_listing_id=listing.root_listing_id,
                    offer_id=listing.crm_offer_id,
                    alert_type="RETRY_EXHAUSTED",
                    message=f"Duplicate takedown hit max retries: {decision.reason}",
                    last_status=status.value))
            except Exception:
                pass
        if decision.should_repost:
            if not RELIST_LIVE:                print(f"  DRY: would repost as gen {decision.next_generation} "
                      f"after {decision.cooldown_seconds}s (set RELIST_LIVE=1 to fire).")
            elif not is_due(listing):
                print(f"  cooling down until {listing.next_eligible_at}.")
            else:
                new_id, new_title = await _fire_replacement(manager, emitter, listing, decision)
                if new_id:
                    listing.superseded_by = new_id
                    listing.next_eligible_at = None
                    try:
                        await dispatch(superseded_event(
                            old_listing_id=listing.current_listing_id,
                            new_listing_id=new_id,
                            offer_id=listing.crm_offer_id,
                            reason=status.value,
                            generation=decision.next_generation,
                            root_listing_id=listing.root_listing_id,
                            new_title=new_title,
                        ))
                    except Exception:
                        pass
                    out_items.append(listing.model_dump(mode="json"))
                    out_items.append(MonitoredListing(
                        crm_offer_id=listing.crm_offer_id,
                        account_id=listing.account_id,
                        current_listing_id=new_id,
                        root_listing_id=listing.root_listing_id,
                        parent_listing_id=listing.current_listing_id,
                        generation=decision.next_generation,
                        title_tpl=listing.title_tpl,
                        desc_tpl=listing.desc_tpl,
                        photo_pool=listing.photo_pool,
                        used_photos=[*listing.used_photos],
                        price=listing.price,
                        category=listing.category,
                        location=listing.location,
                        status=ListingHealthStatus.UNDER_REVIEW,
                    ).model_dump(mode="json"))
                    continue
                listing.next_eligible_at = (
                    datetime.now(UTC) + timedelta(seconds=decision.cooldown_seconds))
                print(f"  repost failed; cooling down until {listing.next_eligible_at}.")
        out_items.append(listing.model_dump(mode="json"))
    state_file.write_text(json.dumps(out_items, indent=2, default=str), encoding="utf-8")
    print(f"state saved: {state_file} ({len(out_items)} entries)")
    return 1 if fatal else 0


async def _fire_replacement(manager, emitter, listing: MonitoredListing, decision) -> tuple[str | None, str]:
    try:
        rep = build_replacement(
            listing.title_tpl or "Test listing {A|B}",
            listing.desc_tpl or "Test description {x|y}",
            listing.photo_pool,
            Path("artifacts/relist"),
            used_photos=listing.used_photos,
        )
    except ValueError as exc:
        print(f"  asset build failed ({exc}); cooling down.")
        return None, ""
    listing.used_photos.append(rep["source_photo"])
    listing.used_photos.append(rep["source_photo"])
    action = MarketplaceCreateAction(manager, emitter, ReceiptStore())
    env = ActionEnvelope(
        action_id=f"relist-{listing.current_listing_id}-g{decision.next_generation}",
        action_type=MarketplaceCreateAction.ACTION_TYPE,
        account_id=listing.account_id,
        input={"title": rep["title"], "price": listing.price, "category": listing.category,
               "description": rep["description"], "location": listing.location,
               "image_paths": [rep["image_path"]], "dry_run": False},
        idempotency_key=f"relist-{listing.current_listing_id}-g{decision.next_generation}",
    )
    out = await action.execute(env)
    if out.published and out.listing_id:
        print(f"  REPUBLISHED {listing.current_listing_id} -> {out.listing_id} "
              f"(pixels_mutated={rep['pixels_mutated']})")
        return out.listing_id, rep["title"]
    print("  publish returned no listing id.")
    return None, ""


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts\\relist_watcher.py <watchlist.json>")
        sys.exit(2)
    from facebook_camofox_client.domain_runtime.locking import SingleFlight

    with SingleFlight("camofox_marketplace") as free:
        if not free:
            print("another browser task holds the lock; skipping tick.")
            sys.exit(0)
        jitter = random.randint(60, 300)
        print(f"jitter {jitter}s (skipped in single-cycle mode)")
        sys.exit(asyncio.run(run_cycle(sys.argv[1], RelistPolicyConfig())))


if __name__ == "__main__":
    main()
