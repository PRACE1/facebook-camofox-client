"""Runtime protocols."""
from typing import Protocol, runtime_checkable
from domain_runtime.models import Cursor, DomainEvent

@runtime_checkable
class CursorRepository(Protocol):
    async def load(self, cursor_key: str, account_id: str, scope_key: str) -> Cursor | None: ...
    async def save(self, cursor: Cursor) -> None: ...

@runtime_checkable
class EventEmitter(Protocol):
    async def emit(self, event_type: str, payload: dict, dedupe_key: str) -> DomainEvent: ...