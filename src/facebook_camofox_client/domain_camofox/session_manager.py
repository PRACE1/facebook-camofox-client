"""Manages Camoufox sessions per account."""
from __future__ import annotations
import uuid


class CamofoxSession:
    def __init__(self, account_id: str, browser) -> None:
        self.account_id = account_id
        self.session_id = str(uuid.uuid4())
        self.browser = browser
        self._closed = False

    async def open_surface(self, surface: str, target: dict):
        if surface != "facebook_group":
            raise ValueError(f"unsupported surface: {surface}")
        url = target.get("url") or f"https://facebook.com/groups/{target['group_id']}"
        page = await self.browser.new_page()
        await page.goto(url)
        return page

    async def execute(self, activity: str, params: dict) -> dict:
        return {"activity": activity, "params": params, "results": []}


class CamofoxSessionManager:
    async def acquire(self, account_id: str, proxy_config: dict | None = None) -> CamofoxSession:
        from camoufox.async_api import AsyncCamoufox

        browser = await AsyncCamoufox(
            humanize=True,
            geoip=True,
            proxy=proxy_config,
        ).__aenter__()
        return CamofoxSession(account_id, browser)

    async def release(self, session: CamofoxSession) -> None:
        if not session._closed:
            await session.browser.close()
            session._closed = True