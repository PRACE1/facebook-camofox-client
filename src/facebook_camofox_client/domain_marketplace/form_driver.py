"""Pure Playwright form driver for /marketplace/create/item.

No business logic, no events — just the DOM mechanics proven in
scripts/spike_marketplace_e2e.py (chevron-opened combobox portal,
aria-disabled polling, trusted keyboard.type for Location).
Takes a duck-typed `page` so unit tests can use fakes.
"""
from __future__ import annotations

import re

LISTBOX = 'div[role="listbox"]'
OPTIONS = 'div[role="listbox"] [role="option"]'
PORTAL = 'div[role="listbox"], div[role="dialog"], div[role="menu"], ul[role="listbox"]'


async def clear_and_type(locator, page, value: str, delay: int = 20) -> None:
    await locator.scroll_into_view_if_needed()
    await locator.click(timeout=8000)
    await page.keyboard.press("ControlOrMeta+A")
    await page.keyboard.press("Backspace")
    await page.keyboard.type(str(value), delay=delay)


async def portal_visible(page, opener=None) -> bool:
    try:
        await page.locator(PORTAL).first.wait_for(state="visible", timeout=1500)
        return True
    except Exception:
        pass
    if opener is not None:
        try:
            return (await opener.get_attribute("aria-expanded")) == "true"
        except Exception:
            return False
    return False


async def open_combobox(page, name: str) -> bool:
    """Open label[role=combobox]. Category is a dialog/popover (no
    aria-haspopup), Condition/Availability are listboxes — accept either."""
    opener = page.locator('label[role="combobox"]', has_text=re.compile(name, re.IGNORECASE)).first
    if await opener.count() == 0:
        return False
    await opener.scroll_into_view_if_needed()
    if await portal_visible(page, opener):
        return True
    try:
        chev = opener.locator("i, svg").first
        if await chev.count() > 0:
            await chev.click(timeout=4000)
            if await portal_visible(page, opener):
                return True
            await page.keyboard.press("Escape")
    except Exception:
        pass
    inners = opener.locator("div, span")
    for i in range(min(await inners.count(), 6)):
        try:
            await inners.nth(i).click(timeout=4000)
            if await portal_visible(page, opener):
                return True
        except Exception:
            pass
        await page.keyboard.press("Escape")
    try:
        await opener.click(timeout=5000)
        if await portal_visible(page, opener):
            return True
    except Exception:
        pass
    await page.keyboard.press("Escape")
    for key in ["ArrowDown", "Enter", "Space"]:
        try:
            await opener.focus(timeout=2000)
            await page.keyboard.press(key)
            if await portal_visible(page, opener):
                return True
        except Exception:
            pass
        await page.keyboard.press("Escape")
    return False


async def pick_option(page, want: str) -> bool:
    norm = lambda s: re.sub(r"[\u2013\u2014\u2212]", "-", s or "").strip().lower()
    if await page.locator(OPTIONS).count() > 0:
        want_n, count = norm(want), await page.locator(OPTIONS).count()
        for i in range(count):
            try:
                if norm(await page.locator(OPTIONS).nth(i).inner_text()) == want_n:
                    await page.locator(OPTIONS).nth(i).click(timeout=5000)
                    return True
            except Exception:
                continue
        for i in range(count):
            try:
                t = norm(await page.locator(OPTIONS).nth(i).inner_text())
                if want_n in t or t in want_n:
                    await page.locator(OPTIONS).nth(i).click(timeout=5000)
                    return True
            except Exception:
                continue
        return False
    # Category taxonomy dialog: search then pick button
    try:
        dlg = page.locator('div[role="dialog"]').last
        if await dlg.count() > 0 and await dlg.is_visible():
            search = dlg.locator('input[placeholder*="Search"], input[type="search"], input[type="text"]').first
            if await search.count() > 0:
                await search.click(timeout=4000)
                await search.fill("", timeout=4000)
                await search.type(want, delay=30)
                await page.wait_for_timeout(1500)
            btn = dlg.get_by_role("button", name=re.compile(re.escape(want), re.IGNORECASE)).first
            if await btn.count() == 0:
                btn = page.get_by_role("button", name=re.compile(re.escape(want), re.IGNORECASE)).first
            await btn.wait_for(state="visible", timeout=8000)
            await btn.click(timeout=5000)
            return True
    except Exception:
        pass
    return False


async def select_combobox(page, name: str, value: str) -> bool:
    if not value:
        return True
    if not await open_combobox(page, name):
        return False
    ok = await pick_option(page, value)
    await page.wait_for_timeout(1000)
    await page.keyboard.press("Escape")
    return ok


async def wait_enabled_and_click(page, name_regex, timeout: int = 15000):
    """div[role=button] never becomes Playwright-'enabled': poll aria-disabled."""
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout / 1000
    btn, last_state = None, "unknown"
    while asyncio.get_event_loop().time() < deadline:
        cands = page.get_by_role("button", name=name_regex)
        picked = None
        for i in range(await cands.count()):
            c = cands.nth(i)
            try:
                if await c.is_visible():
                    picked = c
                    break
            except Exception:
                continue
        if picked is None:
            last_state = "not-visible"
            await page.wait_for_timeout(500)
            continue
        btn = picked
        try:
            aria = await btn.get_attribute("aria-disabled")
            dis = await btn.is_disabled()
            last_state = f"aria-disabled={aria} is_disabled={dis}"
            if aria != "true" and not dis:
                break
        except Exception as exc:
            last_state = f"probe-error {exc}"
        await page.wait_for_timeout(500)
    else:
        raise TimeoutError(f"button {name_regex.pattern} never enabled ({last_state})")
    await btn.scroll_into_view_if_needed()
    await btn.click(timeout=8000)
