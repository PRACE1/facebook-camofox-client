"""Outbound webhooks to Twenty CRM — push, never poll.

Fires on 4 domain transitions: listing.created, listing.health_checked,
listing.superseded, listing.alert_raised. Delivery failure never crashes
the action (returns False, caller logs). Endpoint via
MARKETPLACE_WEBHOOK_URL env; unset = no-op returning None (local dev).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

TIMEOUT_SECONDS = 10


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def created_event(*, listing_id: str, offer_id: str, status: str, generation: int,
                  root_listing_id: str, parent_listing_id: str | None,                   title: str,
                  location_query: str, price: float | int | str,
                  screenshot_url: str | None = None,
                  html_receipt_url: str | None = None) -> dict:
    return {
        "event": "listing.created",
        "timestamp": now_iso(),
        "data": {
            "listingId": listing_id, "offerId": offer_id, "status": status,
            "generation": generation, "rootListingId": root_listing_id,
            "parentListingId": parent_listing_id, "title": title,
            "locationQuery": location_query, "price": price,
            "screenshotUrl": screenshot_url, "htmlReceiptUrl": html_receipt_url,
        },
    }


def health_checked_event(*, listing_id: str, status: str, clicks: int = 0,
                         last_checked_at: str | None = None,
                         next_check_at: str | None = None,
                         last_error: str | None = None) -> dict:
    return {
        "event": "listing.health_checked",
        "timestamp": now_iso(),
        "data": {
            "listingId": listing_id, "status": status, "clicksCount": clicks,
            "lastCheckedAt": last_checked_at or now_iso(),
            "nextCheckAt": next_check_at, "lastError": last_error,
        },
    }


def superseded_event(*, old_listing_id: str, new_listing_id: str, offer_id: str,
                     reason: str, generation: int, root_listing_id: str,
                     new_title: str, new_screenshot_url: str | None = None) -> dict:
    return {
        "event": "listing.superseded",
        "timestamp": now_iso(),
        "data": {
            "oldListingId": old_listing_id, "newListingId": new_listing_id,
            "offerId": offer_id, "reason": reason, "generation": generation,
            "rootListingId": root_listing_id, "newTitle": new_title,
            "newScreenshotUrl": new_screenshot_url,
        },
    }


def alert_raised_event(*, listing_id: str, root_listing_id: str, offer_id: str,
                       alert_type: str, message: str,
                       last_status: str | None = None) -> dict:
    return {
        "event": "listing.alert_raised",
        "timestamp": now_iso(),
        "data": {
            "listingId": listing_id, "rootListingId": root_listing_id,
            "offerId": offer_id, "alertType": alert_type, "message": message,
            "lastStatus": last_status,
        },
    }


async def dispatch(payload: dict, url: str | None = None) -> bool | None:
    """POST one webhook. None = no endpoint configured (dev no-op).
    False = delivery failed (logged, never raised). True = delivered."""
    url = url or os.getenv("MARKETPLACE_WEBHOOK_URL")
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload)
            return 200 <= resp.status_code < 300
    except Exception:
        return False


def post_new_event(*, action_id: str, group_id: str, record_id: str,
                   post_id: str, content: str = "", url: str = "",
                   author: str = "", occurred_at: str | None = None) -> dict:
    """Inbound notification: a new group post passed filters + commit."""
    return {
        "event": "posts.new",
        "timestamp": now_iso(),
        "data": {
            "actionId": action_id, "groupId": group_id, "recordId": record_id,
            "postId": post_id, "content": (content or "")[:500],
            "url": url, "author": author, "occurredAt": occurred_at,
        },
    }
