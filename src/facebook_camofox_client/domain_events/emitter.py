"""Event emitter."""
from __future__ import annotations
from datetime import datetime, UTC
from facebook_camofox_client.domain_events.models import DomainEvent

class InMemoryEventEmitter:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def emit(self, event_type: str, payload: dict, dedupe_key: str) -> DomainEvent:
        ev = DomainEvent(event_type=event_type, action_id=payload.get("action_id", ""), record_id=payload.get("record_id"), dedupe_key=dedupe_key, payload=payload)
        self.events.append(ev)
        return ev