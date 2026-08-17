"""Cursor repository."""
from __future__ import annotations
from domain_cursors.models import Cursor

class InMemoryCursorRepository:
    def __init__(self) -> None:
        self._store: dict[str, Cursor] = {}

    def _key(self, cursor_key: str, account_id: str, scope_key: str) -> str:
        return f"{cursor_key}:{account_id}:{scope_key}"

    async def load(self, cursor_key: str, account_id: str, scope_key: str) -> Cursor | None:
        return self._store.get(self._key(cursor_key, account_id, scope_key))

    async def save(self, cursor: Cursor) -> None:
        self._store[self._key(cursor.cursor_key, cursor.account_id, cursor.scope_key)] = cursor