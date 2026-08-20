from __future__ import annotations
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
        page = await self.context.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        return page

    async def execute(self, activity: str, params: dict[str, Any]) -> dict[str, Any]:
        if activity == "facebook_group_search":
            from facebook_camofox_client.domain_extraction.response_capture import NativeResponseAdapter
            from facebook_camofox_client.domain_extraction.post_extractor import PostExtractor

            page = await self.context.new_page()
            adapter = NativeResponseAdapter(page)
            await adapter.start_capture()

            url = params.get("url") or f"https://facebook.com/groups/{params.get('group_id', '')}"
            await page.goto(url, wait_until="domcontentloaded")

            scroll_limit = params.get("scroll_limit", 3)
            for _ in range(scroll_limit):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

            raw_responses = await adapter.stop_capture()
            extractor = PostExtractor()
            posts = extractor.extract(raw_responses, params.get("terms", []))
            return {"activity": activity, "params": params, "results": posts}

        raise NotImplementedError(f"unsupported activity: {activity}")


class CamofoxSessionManager:
    async def acquire(
        self,
        account_id: str,
        proxy_config: dict[str, Any] | None = None,
        storage_state_path: str | None = None,
    ) -> CamofoxSession:
        from camoufox.async_api import AsyncCamoufox

        runtime = AsyncCamoufox(
            humanize=True,
            geoip=True,
            proxy=proxy_config,
        )
        browser = await runtime.__aenter__()
        context_kwargs: dict[str, Any] = {}
        if storage_state_path:
            context_kwargs["storage_state"] = str(Path(storage_state_path))
        context = await browser.new_context(**context_kwargs)
        return CamofoxSession(account_id, runtime, browser, context)

    async def release(self, session: CamofoxSession) -> None:
        if session._closed:
            return
        session._closed = True
        try:
            await session.context.close()
        finally:
            await session.runtime.__aexit__(None, None, None)