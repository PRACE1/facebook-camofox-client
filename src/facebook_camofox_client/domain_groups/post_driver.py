"""Group composer driver — fallback chains, no business logic.

Ground truth NOT yet verified live for group 305056891435827: run
scripts/run_group_post_dryrun.py first and pin selectors from the
composer_filled_*.html dump. Chains below are best-effort ordered guesses
from the marketplace driver experience (placeholder/label/role, never one
hard selector).
"""
from __future__ import annotations

import re
from pathlib import Path


async def _first_visible(page, locators):
    for loc in locators:
        try:
            c = loc.first if hasattr(loc, "first") else loc
            if await c.count() and await c.is_visible():
                return c
        except Exception:
            continue
    return None


async def open_composer(page) -> object | None:
    """Click the 'Write something...' trigger so the full editor mounts."""
    rx = re.compile(r"write something|what.s on your mind|create.*post", re.I)
    cands = [
        page.get_by_text(rx).first,
        page.locator('[aria-label*="Write"]').first,
        page.locator('div[role="textbox"]').first,
    ]
    trigger = await _first_visible(page, cands)
    if trigger is None:
        return None
    try:
        await trigger.click(timeout=5000)
        await page.wait_for_timeout(1500)
    except Exception:
        pass
    return trigger


async def fill_composer(page, message: str, image_paths: list[str] | None = None) -> bool:
    await open_composer(page)
    rx_exact = re.compile(r"^(write something.*|what.s on your mind.*)$", re.I)
    editor = await _first_visible(page, [
        page.get_by_role("textbox").first,
        page.locator('div[role="textbox"][contenteditable="true"]').first,
        page.locator('[aria-label*="Write"]').first,
    ])
    if editor is None or not message:
        return editor is not None
    try:
        await editor.click(timeout=5000)
    except Exception:
        pass
    try:
        await page.keyboard.press("ControlOrMeta+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(message, delay=15)
    except Exception:
        try:
            await editor.fill(message, timeout=5000)
        except Exception:
            return False
    if image_paths:
        existing = [p for p in image_paths if Path(p).exists()]
        if not existing:
            return False
        file_input = page.locator('input[type="file"][accept*="image"]').first
        if await file_input.count() == 0:
            return False
        await file_input.set_input_files(existing)
        await page.wait_for_timeout(3000)
    _ = rx_exact  # kept for dump-grep pinning after first dry-run
    return True


async def wait_enabled_and_click(page, name_regex, timeout: int = 15000):
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
