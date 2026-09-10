"""Seller-dashboard health check — the spec's correction to public-URL polling.

Public item pages cache status for hours; the dashboard (/you/selling)
badges are source of truth. Maps card text -> ListingHealthStatus.
"""
from __future__ import annotations

import re

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


_CARD_JS = """(title) => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  // anchor on ONE long word: titles wrap across elements, so a multi-word
  // conjunction can never match a single node.
  const anchor = (norm(title).toLowerCase().split(/[^a-z]+/).find(w => w.length >= 5)) || '';
  if (!anchor) return '';
  const els = [...document.querySelectorAll('div,span')].filter(
    e => e.children.length === 0 && norm(e.textContent).toLowerCase().includes(anchor));
  for (const el of els) {
    let p = el.parentElement, depth = 0, txt = '';
    while (p && depth < 8) { txt = norm(p.innerText); if (txt.length > 120) break; p = p.parentElement; depth++; }
    if (/active|review|duplicate|sold|pending|clicks on listing/i.test(txt)) return txt.slice(0, 800);
  }
  return '';
}"""


async def check_dashboard_health(page, listing_id: str, title: str = "") -> tuple[ListingHealthStatus, str]:
    """Open you/selling, find the card by exact title text (cards are NOT
    anchors — zero /item/ hrefs on the dashboard), classify its badges.
    Returns (status, card_text). Missing card on a healthy dashboard with
    other cards -> DELETED_BY_FB; else UNKNOWN (never fabricate)."""
    await page.goto("https://www.facebook.com/marketplace/you/selling",
                    wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)
    try:  # land on Seller dashboard by default; cards live under Your listings
        tab = page.get_by_text(re.compile(r"^Your listings$", re.IGNORECASE)).first
        if await tab.count() > 0:
            await tab.click(timeout=5000)
            await page.wait_for_timeout(2000)
    except Exception:
        pass
    for _ in range(8):
        try:
            await page.evaluate("window.scrollBy(0, 900)")
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        if title:
            try:
                card = await page.evaluate(_CARD_JS, title)
                if card:
                    return classify_dashboard_card(card, still_listed=True), card
            except Exception:
                pass
    try:
        body = await page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ListingHealthStatus.UNKNOWN, ""
    low_body = (body or "").lower()
    # other cards rendered but ours is absent -> genuinely gone
    if ("your listings" in low_body
            and ("clicks on listing" in low_body or "mark as sold" in low_body)
            and (not title or title.lower() not in low_body)):
        return ListingHealthStatus.DELETED_BY_FB, ""
    return ListingHealthStatus.UNKNOWN, ""
