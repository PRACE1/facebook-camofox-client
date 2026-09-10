"""Seller-dashboard health check — the spec's correction to public-URL polling.

Public item pages cache status for hours; the dashboard (/you/selling)
badges are source of truth. Maps card text -> ListingHealthStatus.
"""
from __future__ import annotations

from facebook_camofox_client.domain_marketplace.relist import ListingHealthStatus


def classify_dashboard_card(card_text: str, still_listed: bool = True) -> ListingHealthStatus:
    low = (card_text or "").lower()
    if "unable to buy or sell" in low or "commerce ban" in low or "account restricted" in low:
        return ListingHealthStatus.COMMERCE_BAN
    if "against our commerce policies" in low or "goes against" in low:
        return ListingHealthStatus.POLICY_VIOLATION
    if "verify" in low and ("identity" in low or "checkpoint" in low or "confirm" in low):
        return ListingHealthStatus.CHECKPOINT_REQUIRED
    if "duplicate" in low:
        return ListingHealthStatus.DUPLICATE_TAKEDOWN
    if "mark as sold" in low and "sold" in low and "active" not in low:
        return ListingHealthStatus.SOLD
    if "sold" in low and "active" not in low:
        return ListingHealthStatus.SOLD
    if "being reviewed" in low or "in review" in low:
        return ListingHealthStatus.UNDER_REVIEW
    if "active" in low:
        return ListingHealthStatus.ACTIVE
    if not still_listed:
        return ListingHealthStatus.DELETED_BY_FB
    return ListingHealthStatus.UNKNOWN


async def check_dashboard_health(page, listing_id: str) -> tuple[ListingHealthStatus, str]:
    """Open you/selling, find the card linking to listing_id, classify it.
    Returns (status, card_text). Never fabricates: missing card -> UNKNOWN
    unless the dashboard loaded fine with other cards (then DELETED_BY_FB)."""
    await page.goto("https://www.facebook.com/marketplace/you/selling",
                    wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)
    for _ in range(6):
        try:
            await page.evaluate("window.scrollBy(0, 900)")
        except Exception:
            pass
        await page.wait_for_timeout(2000)
    try:
        hrefs = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href*="/marketplace/item/"]')).map(a=>({href:a.getAttribute('href')||'',card:(a.innerText||'').slice(0,300)}))""")
    except Exception:
        return ListingHealthStatus.UNKNOWN, ""
    mine = [h for h in hrefs if listing_id in (h.get("href") or "")]
    if mine:
        return classify_dashboard_card(mine[0].get("card", ""), still_listed=True), mine[0].get("card", "")
    try:
        body = await page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ListingHealthStatus.UNKNOWN, ""
    if "your listings" in (body or "").lower() and listing_id not in (body or ""):
        # dashboard healthy but our card is gone
        if hrefs:
            return ListingHealthStatus.DELETED_BY_FB, ""
    return ListingHealthStatus.UNKNOWN, ""
