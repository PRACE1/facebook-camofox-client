"""Group post action — same lifecycle shape as PostsListenAction.

acquire -> open group surface -> auth check -> composer fill via driver ->
receipt -> emit groups.post_completed / groups.post_failed -> release.
Composer selectors are fallback chains (unverified live until dry-run dump).
"""
from __future__ import annotations

import re
from pathlib import Path

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_groups import post_driver as driver


class GroupPostAction:
    ACTION_TYPE = "groups.post"

    def __init__(self, session_manager, event_emitter, receipt_store=None) -> None:
        self.session_manager = session_manager
        self.event_emitter = event_emitter
        self.receipt_store = receipt_store

    async def _save_debug(self, page, name: str) -> None:
        if self.receipt_store is not None:
            try:
                await self.receipt_store.save_debug(page, name)
            except Exception:
                pass

    async def execute(self, envelope: ActionEnvelope) -> dict:
        from facebook_camofox_client.domain_groups.schemas import (
            GroupPostInput,
            GroupPostOutput,
        )

        data = GroupPostInput(**envelope.input)
        session = await self.session_manager.acquire(envelope.account_id)
        try:
            page = await session.new_page()
            await page.goto(
                f"https://www.facebook.com/groups/{data.group_id}",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3000)
            title = ""
            try:
                title = await page.title()
            except Exception:
                pass
            if "login" in page.url.lower() or "log in" in (title or "").lower():
                await self.event_emitter.emit(
                    "groups.post_failed",
                    {"action_id": envelope.action_id, "reason": "auth_required"},
                    dedupe_key=f"{envelope.action_id}-failed",
                )
                return GroupPostOutput(posted=False).model_dump()

            if not await driver.fill_composer(page, data.message, data.image_paths):
                await self._save_debug(page, f"composer_miss_{envelope.action_id}")
                await self.event_emitter.emit(
                    "groups.post_failed",
                    {"action_id": envelope.action_id, "reason": "composer_not_found"},
                    dedupe_key=f"{envelope.action_id}-failed",
                )
                return GroupPostOutput(posted=False).model_dump()

            await self._save_debug(page, f"composer_filled_{envelope.action_id}")
            if data.dry_run:
                await self.event_emitter.emit(
                    "groups.post_completed",
                    {"action_id": envelope.action_id, "dry_run": True, "posted": False},
                    dedupe_key=f"{envelope.action_id}-completed",
                )
                return GroupPostOutput(posted=False).model_dump()

            await driver.wait_enabled_and_click(page, re.compile(r"^Post$", re.I))
            await page.wait_for_timeout(5000)
            await self._save_debug(page, f"after_post_{envelope.action_id}")
            await self.event_emitter.emit(
                "groups.post_completed",
                {"action_id": envelope.action_id, "posted": True,
                 "group_id": data.group_id},
                dedupe_key=f"{envelope.action_id}-completed",
            )
            return GroupPostOutput(posted=True, group_id=data.group_id).model_dump()
        except Exception as exc:
            await self.event_emitter.emit(
                "groups.post_failed",
                {"action_id": envelope.action_id, "reason": str(exc)},
                dedupe_key=f"{envelope.action_id}-failed",
            )
            raise
        finally:
            await self.session_manager.release(session)
