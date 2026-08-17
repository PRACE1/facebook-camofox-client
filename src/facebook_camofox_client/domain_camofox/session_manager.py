"""Manages AsyncCamoufox sessions per account."""
from __future__ import annotations
import uuid
from camofox.async_api import AsyncCamoufox

class CamofoxSession:
    """Wrapper around AsyncCamoufox browser session."""

    def __init__(self, account_id: str, browser: AsyncCamoufox) -> None:
        self.account_id = account_id
        self.session_id = str(uuid.uuid4())
        self.browser = browser
        self._ready = False

    async def ensure_ready(self) -> dict:
        self._ready = True
        return {"status": "ready", "session_id": self.session_id}

    async def auth_guard(self) -> dict:
        return {"authenticated": True}

    async def open_surface(self, surface: str, target: dict) -> None:
        page = await self.browser.new_page()
        if surface == "facebook_group":
            group_id = target.get("group_id", "")
            url = target.get("url") or f"https://facebook.com/groups/{group_id}"
            await page.goto(url)

    async def execute(self, activity: str, params: dict) -> dict:
        return {"activity": activity, "params": params, "results": []}

    async def close(self) -> None:
        await self.browser.stop()

class CamofoxSessionManager:
    """Acquires and releases account-scoped Camofox sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, CamofoxSession] = {}

    async def acquire(self, account_id: str, proxy_config: dict | None = None) -> CamofoxSession:
        browser = await AsyncCamoufox(humanize=True, geoip=True, proxy=proxy_config).__aenter__()
        session = CamofoxSession(account_id=account_id, browser=browser)
        self._sessions[session.session_id] = session
        return session

    async def release(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            await session.browser.__aexit__(None, None, None)