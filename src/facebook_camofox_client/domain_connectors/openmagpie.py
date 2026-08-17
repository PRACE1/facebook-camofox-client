"""Adapter to wire into OpenMagpie."""
from __future__ import annotations
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import ClassVar
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_actions.runner import ActionRunner
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.search import GroupsSearchAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer

class FacebookCamofoxConnector:
    kind: ClassVar[str] = "facebook_search"

    def __init__(self) -> None:
        self.runner = ActionRunner()
        self.session_manager = CamofoxSessionManager()
        self.cursor_repo = InMemoryCursorRepository()
        self.emitter = InMemoryEventEmitter()
        self.normalizer = PostNormalizer()
        search = GroupsSearchAction(self.session_manager, self.cursor_repo, self.normalizer, self.emitter)
        self.runner.register("groups.search", search.execute)

    async def poll(self, spec: dict, since: datetime | None = None) -> Iterator[dict]:
        envelope = ActionEnvelope(action_id=f"poll-{datetime.now().timestamp()}", action_type="groups.search", account_id=spec.get("account_id", "default"), input=spec, idempotency_key=f"poll-{spec.get('page_url', '')}-{since}")
        result = await self.runner.run(envelope)
        for record in result.get("results", []):
            yield record