"""Primitive browser interactions: every act is ease -> hover -> act.

The element is eased into view along a bell-curve scroll trajectory
(never an instant jump), the cursor glides to its center with a
micro-orbit hover on randomized timing, and only then does the
fill/click happen. Raw locator.click()/fill() as primary motion is
banned outside this module; everything routes through fill_first /
click_first. Under CAMOFOX_ENFORCE_PRIMITIVES=1, fallbacks raise and a
missing hover aborts; every resolved ref prints a receipt with
CAMOFOX_PRINT_REFS=1.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

from facebook_camofox_client.domain_camofox.primitives import (
    RefReceipt,
    enforce_primitives,
    jitter_delay,
    record_ref,
)

LOGGER = logging.getLogger("facebook-camofox.interactions")
MOUSE_MOVE_TIMEOUT_SECONDS = 5.0


async def human_move(page: Any, x: float, y: float,
                     timeout: float = MOUSE_MOVE_TIMEOUT_SECONDS) -> bool:
    try:
        await asyncio.wait_for(page.mouse.move(x, y), timeout=timeout)
        return True
    except (Exception, asyncio.TimeoutError) as exc:
        LOGGER.debug("human_move failed (%s)", type(exc).__name__)
        if enforce_primitives():
            raise RuntimeError(f"cursor move to ({x:.0f},{y:.0f}) failed") from exc
        return False


async def ease_into_view(page: Any, selector: str) -> bool:
    try:
        from facebook_camofox_client.domain_camofox.scroll import scroll_to_selector

        result = await scroll_to_selector(page, selector)
        return bool(result.get("ok"))
    except Exception as exc:
        LOGGER.debug("trajectory scroll failed (%s)", type(exc).__name__)
        if enforce_primitives():
            raise
    try:
        loc = page.locator(selector).first
        await loc.scroll_into_view_if_needed(timeout=5000)
        return True
    except Exception:
        return False


async def hover_locator(page: Any, locator: Any, selector: str = "") -> RefReceipt:
    """Glide to the element center, micro-orbit, record the ref receipt."""
    ref = RefReceipt(selector=selector or "<locator>")
    try:
        box = await locator.bounding_box()
    except Exception:
        box = None
    if not box:
        if enforce_primitives():
            raise RuntimeError(f"no bounding box for {ref.selector!r}; hover aborted")
        return record_ref(ref)
    ref.x = box["x"] + box["width"] / 2
    ref.y = box["y"] + box["height"] / 2
    ref.width, ref.height = box["width"], box["height"]
    ref.resolved_at = time.time()
    ok = await human_move(page, ref.x, ref.y)
    if ok:
        try:  # micro-orbit: 2 off-center drifts on jittered timing
            for _ in range(2):
                dx = random.uniform(-6, 6)
                dy = random.uniform(-4, 4)
                await asyncio.sleep(jitter_delay(120, 0.4) / 1000)
                await asyncio.wait_for(
                    page.mouse.move(ref.x + dx, ref.y + dy),
                    timeout=MOUSE_MOVE_TIMEOUT_SECONDS,
                )
            await asyncio.sleep(jitter_delay(150, 0.4) / 1000)
            await asyncio.wait_for(
                page.mouse.move(ref.x, ref.y), timeout=MOUSE_MOVE_TIMEOUT_SECONDS)
        except (Exception, asyncio.TimeoutError):
            ok = False
    ref.ok = ok
    ref.acted_at = time.time()
    if not ok and enforce_primitives():
        record_ref(ref)
        raise RuntimeError(f"hover failed for {ref.selector!r}; act aborted")
    return record_ref(ref)


async def reach(page: Any, selector: str, locator: Any) -> bool:
    """Full approach: ease into view, hover center. True if visible after."""
    await ease_into_view(page, selector)
    await hover_locator(page, locator, selector)
    try:
        return bool(await locator.is_visible())
    except Exception:
        return False


async def _first_visible(page: Any, selectors: list[str]):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return sel, loc
        except Exception:
            continue
    return None, None


async def fill_first(page: Any, selectors: list[str], value: str) -> bool:
    sel, loc = await _first_visible(page, selectors)
    if loc is None or sel is None:
        return False
    try:
        await reach(page, sel, loc)
        await loc.fill(value)
        return True
    except Exception:
        return False


async def click_first(page: Any, selectors: list[str]) -> bool:
    sel, loc = await _first_visible(page, selectors)
    if loc is None or sel is None:
        return False
    try:
        await reach(page, sel, loc)
        await loc.click(timeout=5000)
        return True
    except Exception:
        return False
