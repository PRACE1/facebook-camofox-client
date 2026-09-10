"""Marketplace status (activity) checker — read-only polling of one listing.

Classifies from the rendered item page, never fabricates: anything
unrecognized stays "unknown" with the observed title for evidence.
"""
from __future__ import annotations

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_marketplace.schemas import (
    MarketplaceStatusInput,
    MarketplaceStatusOutput,
)


def classify_status(url: str, title: str, body: str) -> str:
    low_url, low_body = (url or "").lower(), (body or "").lower()
    if "login" in low_url:
        return "login-wall"
    if "duplicate listing" in low_body:
        return "under-review-duplicate"
    if "being reviewed" in low_body or "in review" in low_body:
        return "under-review"
    if "sold" in low_body and "mark as sold" not in low_body:
        return "sold"
    if "not available" in low_body or "removed" in low_body or "not found" in low_body:
        return "removed"
    if (title or "").strip():
        return "active"
    return "unknown"


class MarketplaceStatusAction:
    ACTION_TYPE = "marketplace.status"

    def __init__(self, session_manager, event_emitter) -> None:
        self.session_manager = session_manager
        self.event_emitter = event_emitter

    async def execute(self, envelope: ActionEnvelope) -> MarketplaceStatusOutput:
        data = MarketplaceStatusInput(**envelope.input)
        url = f"https://www.facebook.com/marketplace/item/{data.listing_id}/"
        session = await self.session_manager.acquire(envelope.account_id)
        try:
            page = await session.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            final_url = page.url
            try:
                title = await page.title()
            except Exception:
                title = ""
            try:
                body = await page.locator("body").inner_text(timeout=5000)
            except Exception:
                body = ""
            status = classify_status(final_url, title, body or "")
            await self.event_emitter.emit(
                "marketplace.status_checked",
                {"action_id": envelope.action_id, "listing_id": data.listing_id,
                 "status": status},
                dedupe_key=f"{envelope.action_id}-{data.listing_id}",
            )
            return MarketplaceStatusOutput(
                listing_id=data.listing_id, listing_url=final_url,
                status=status, title=(title or None),
            )
        except Exception as exc:
            await self.event_emitter.emit(
                "marketplace.status_failed",
                {"action_id": envelope.action_id, "listing_id": data.listing_id,
                 "reason": str(exc)},
                dedupe_key=f"{envelope.action_id}-{data.listing_id}-failed",
            )
            raise
        finally:
            await self.session_manager.release(session)
