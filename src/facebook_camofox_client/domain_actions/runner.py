"""Action runner dispatches envelopes to handlers."""
from __future__ import annotations
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope

class ActionRunner:
    def __init__(self) -> None:
        self._handlers: dict[str, callable] = {}

    def register(self, action_type: str, handler: callable) -> None:
        self._handlers[action_type] = handler

    async def run(self, envelope: ActionEnvelope) -> dict:
        handler = self._handlers.get(envelope.action_type)
        if not handler:
            raise ValueError(f"No handler for: {envelope.action_type}")
        envelope.status = "running"
        result = await handler(envelope)
        envelope.status = "completed"
        return result