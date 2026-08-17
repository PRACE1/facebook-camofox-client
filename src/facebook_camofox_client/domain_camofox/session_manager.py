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
        return {"activity": activity, "params": params, "results": []}


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