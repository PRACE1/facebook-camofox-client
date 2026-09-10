from __future__ import annotations
import os
import uuid
from pathlib import Path
from typing import Any


class CamofoxSession:
    def __init__(self, account_id: str, runtime: Any, browser: Any, context: Any) -> None:
        self.account_id = account_id
        self.session_id = str(uuid.uuid4())
        self.runtime = runtime
        self.browser = browser
        self.context = context
        self._closed = False

    async def open_surface(self, surface: str, target: dict[str, Any]):
        if surface != "facebook_group":
            raise ValueError(f"unsupported surface: {surface}")
        url = target.get("url") or f"https://facebook.com/groups/{target['group_id']}"
        page = await self.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        return page

    async def new_page(self):
        """Raw page for write actions (marketplace create/status).

        Read actions go through open_surface/execute; write actions need
        direct page access for the combobox-portal form driver."""
        return await self.context.new_page()

    async def execute(self, activity: str, params: dict[str, Any]) -> dict[str, Any]:
        if activity == "facebook_group_search":
            from facebook_camofox_client.domain_extraction.post_extractor import extract_from_relay
            from facebook_camofox_client.domain_extraction.response_capture import NativeResponseAdapter

            group_id = params.get("group_id")
            if not group_id:
                group_ids = params.get("group_ids", [])
                if group_ids:
                    group_id = group_ids[0]

            if not group_id:
                raise ValueError("group_id or group_ids required for facebook_group_search")

            page = await self.context.new_page()
            adapter = NativeResponseAdapter(expected_group_id=group_id)

            adapter.attach(page)
            adapter.start()

            try:
                url = params.get("url") or f"https://web.facebook.com/groups/{group_id}"
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                html = await page.content()
                relay_result = extract_from_relay(html, group_id, min_records=0)
                adapter.merge_external(relay_result.records)

                adapter.mark_scroll_started()

                scroll_limit = params.get("scroll_limit", 3)
                for _ in range(scroll_limit):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)

            finally:
                await adapter.stop()

            records = adapter.snapshot()

            min_records = params.get("limit", 3)
            degraded = adapter.has_scroll_phase_drops or len(records) < min_records

            return {
                "activity": activity,
                "params": params,
                "results": records,
                "counters": adapter.counters,
                "degraded": degraded,
                "warning": (
                    f"{adapter.counters['scroll_phase_dropped']} response(s) dropped during scroll"
                    if adapter.has_scroll_phase_drops else None
                ),
            }

        raise NotImplementedError(f"unsupported activity: {activity}")


class CamofoxSessionManager:
    async def acquire(
        self,
        account_id: str,
        proxy_config: dict[str, Any] | None = None,
        storage_state_path: str | None = None,
        cookies: list[dict] | None = None,
    ) -> CamofoxSession:
        """cookies: raw CRM Chrome-export list, injected in-process via
        cookie_hydration (takes precedence over storage_state file)."""
        from camoufox.async_api import AsyncCamoufox

        runtime = AsyncCamoufox(
            humanize=True,
            geoip=True,
            proxy=proxy_config,
        )
        browser = await runtime.__aenter__()
        context_kwargs: dict[str, Any] = {}
        if cookies is None:
            storage_state_path = storage_state_path or os.getenv(
                f"CAMOFOX_STORAGE_STATE_{account_id.upper().replace('-', '_')}"
            )
            if storage_state_path:
                context_kwargs["storage_state"] = str(Path(storage_state_path))
        context = await browser.new_context(**context_kwargs)
        if cookies is not None:
            from facebook_camofox_client.domain_camofox.cookie_hydration import (
                hydrate_context,
            )
            await hydrate_context(context, cookies)
        return CamofoxSession(account_id, runtime, browser, context)

    async def release(self, session: CamofoxSession) -> None:
        if session._closed:
            return
        session._closed = True
        try:
            await session.context.close()
        finally:
            await session.runtime.__aexit__(None, None, None)
