"""Storage interface for cursors — must be implemented before cursors advance.

The invariant: records COMMIT before the cursor advances.
InMemory is the dev implementation. SQLite or Postgres plugs in here.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from facebook_camofox_client.domain_cursors.models import Cursor


class CursorRepository(ABC):
    """Abstract storage interface. Records must be persisted before save() is called."""

    @abstractmethod
    async def load(self, cursor_key: str, account_id: str, scope_key: str) -> Cursor | None:
        """Load the current high-watermark cursor, or None if first run."""

    @abstractmethod
    async def save(self, cursor: Cursor) -> None:
        """Persist cursor. Must only be called after records are committed."""


class InMemoryCursorRepository(CursorRepository):
    """Dev/test implementation — not durable across restarts."""

    def __init__(self) -> None:
        self._store: dict[str, Cursor] = {}

    def _key(self, cursor_key: str, account_id: str, scope_key: str) -> str:
        return f"{account_id}:{cursor_key}:{scope_key}"

    async def load(self, cursor_key: str, account_id: str, scope_key: str) -> Cursor | None:
        return self._store.get(self._key(cursor_key, account_id, scope_key))

    async def save(self, cursor: Cursor) -> None:
        key = self._key(cursor.cursor_key, cursor.account_id, cursor.scope_key)
        self._store[key] = cursor