"""Marketplace create action — same lifecycle shape as PostsListenAction.

acquire -> auth check -> fill via injected driver -> receipt ->
emit marketplace.create_completed / marketplace.create_failed -> release.
The Playwright driver is injected so unit tests use fakes (no browser).
"""
from __future__ import annotations

import re
from pathlib import Path

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_marketplace import form_driver as driver
from facebook_camofox_client.domain_marketplace.categories import resolve_category
from facebook_camofox_client.domain_marketplace.receipts import now_iso
from facebook_camofox_client.domain_marketplace.schemas import (
    MarketplaceCreateInput,
    MarketplaceCreateOutput,
)


class MarketplaceCreateAction:
    ACTION_TYPE = "marketplace.create"

    def __init__(self, session_manager, event_emitter, receipt_store=None) -> None:
        self.session_manager = session_manager
        self.event_emitter = event_emitter
        self.receipt_store = receipt_store

    async def _save_debug(self, page, name: str):
        if self.receipt_store is not None:
            try:
                return await self.receipt_store.save_debug(page, name)
            except Exception:
                pass
        return None

    async def execute(self, envelope: ActionEnvelope) -> MarketplaceCreateOutput:
        data = MarketplaceCreateInput(**envelope.input)
        category = resolve_category(data.category)
        if category is None:
            await self.event_emitter.emit(
                "marketplace.create_failed",
                {"action_id": envelope.action_id, "reason": "unknown_category",
                 "category": data.category},
                dedupe_key=f"{envelope.action_id}-failed",
            )
            return MarketplaceCreateOutput(published=False, reason="unknown_category")
        session = await self.session_manager.acquire(envelope.account_id)
        try:
            page = await session.new_page()
            await page.goto(
                "https://www.facebook.com/marketplace/create/item",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3000)
            if "login" in page.url.lower():
                await self.event_emitter.emit(
                    "marketplace.create_failed",
                    {"action_id": envelope.action_id, "reason": "auth_required"},
                    dedupe_key=f"{envelope.action_id}-failed",
                )
                return MarketplaceCreateOutput(published=False, reason="auth_required")

            opened = False
            for _attempt in range(3):
                if await driver.select_combobox(page, "Category", category):
                    opened = True
                    break
                try:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass
            if not opened:
                await self._save_debug(page, f"category_miss_{envelope.action_id}")
                await self.event_emitter.emit(
                    "marketplace.create_failed",
                    {"action_id": envelope.action_id, "reason": "category_not_opened"},
                    dedupe_key=f"{envelope.action_id}-failed",
                )
                return MarketplaceCreateOutput(published=False, reason="category_not_opened")

            file_input = page.locator('input[type="file"][accept*="image"]').first
            existing = [p for p in data.image_paths if Path(p).exists()]
            if existing:
                await file_input.set_input_files(existing)
                await page.wait_for_timeout(3000)
            elif data.image_paths:
                # Photos gate Next (0/10 keeps it disabled) — fail loud, not silent.
                await self._save_debug(page, f"no_images_{envelope.action_id}")
                await self.event_emitter.emit(
                    "marketplace.create_failed",
                    {"action_id": envelope.action_id, "reason": "images_not_found"},
                    dedupe_key=f"{envelope.action_id}-failed",
                )
                return MarketplaceCreateOutput(published=False, reason="images_not_found")

            texts = page.locator('input[type="text"]:not([role="combobox"])')
            await texts.first.wait_for(state="visible", timeout=10000)
            await driver.clear_and_type(texts.nth(0), page, data.title)
            await driver.clear_and_type(texts.nth(1), page, data.price)
            if data.condition:
                await driver.select_combobox(page, "Condition", data.condition)
            if data.description:
                desc = page.locator("textarea").first
                await desc.wait_for(state="visible", timeout=10000)
                await driver.clear_and_type(desc, page, data.description, delay=10)
            if data.location:
                loc = page.locator('input[role="combobox"][aria-label="Location"]').first
                await loc.wait_for(state="visible", timeout=10000)
                await loc.click(timeout=8000)
                await page.keyboard.press("ControlOrMeta+A")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(data.location, delay=30)
                await page.wait_for_timeout(1500)
                try:
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                except Exception:
                    pass

            filled = await self._save_debug(page, f"form_filled_{envelope.action_id}")
            if data.dry_run:
                await self.event_emitter.emit(
                    "marketplace.create_completed",
                    {"action_id": envelope.action_id, "dry_run": True, "published": False},
                    dedupe_key=f"{envelope.action_id}-completed",
                )
                return MarketplaceCreateOutput(
                    published=False, success=True,
                    receipt_path=filled.screenshot_path if filled else None,
                )

            await driver.wait_enabled_and_click(page, re.compile(r"^Next$", re.IGNORECASE))
            await page.wait_for_timeout(3000)
            await driver.wait_enabled_and_click(
                page, re.compile(r"^(Publish|Share|Post)$", re.IGNORECASE), timeout=15000)
            await page.wait_for_timeout(5000)
            shot = await self._save_debug(page, f"after_publish_{envelope.action_id}")

            final_url = page.url
            m = re.search(r"/item/(\d+)", final_url)
            listing_id = m.group(1) if m else await self._capture_dashboard_id(page)
            output = MarketplaceCreateOutput(
                published=True,
                success=listing_id is not None,
                listing_id=listing_id,
                listing_url=final_url if listing_id else None,
                published_at=now_iso(),
                receipt_path=shot.screenshot_path if shot else None,
            )
            await self.event_emitter.emit(
                "marketplace.create_completed",
                {"action_id": envelope.action_id, "listing_id": listing_id,
                 "published": True},
                dedupe_key=f"{envelope.action_id}-completed",
            )
            try:
                from facebook_camofox_client.domain_marketplace.webhooks import (
                    created_event,
                    dispatch,
                )
                try:
                    price_num: float | int | str = int(str(data.price).lstrip("Pp€£$ "))
                except ValueError:
                    try:
                        price_num = float(str(data.price))
                    except ValueError:
                        price_num = data.price
                await dispatch(created_event(
                    listing_id=listing_id or "", offer_id=data.offer_id,
                    status="UNDER_REVIEW", generation=0,
                    root_listing_id=listing_id or "",
                    parent_listing_id=None, title=data.title,
                    location_query=data.location, price=price_num,
                    screenshot_url=output.receipt_path))
            except Exception:
                pass
            return output
        except Exception as exc:
            await self.event_emitter.emit(
                "marketplace.create_failed",
                {"action_id": envelope.action_id, "reason": str(exc)},
                dedupe_key=f"{envelope.action_id}-failed",
            )
            raise
        finally:
            await self.session_manager.release(session)

    async def _capture_dashboard_id(self, page) -> str | None:
        """Seller dashboard opens a modal (no navigation): parse item hrefs."""
        for _ in range(10):
            try:
                hrefs = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('a[href*="/marketplace/item/"]')).map(a=>a.getAttribute('href')||'')""")
                for h in hrefs:
                    m = re.search(r"/item/(\d+)", h or "")
                    if m:
                        return m.group(1)
            except Exception:
                pass
            try:
                await page.wait_for_timeout(1000)
            except Exception:
                break
        return None
