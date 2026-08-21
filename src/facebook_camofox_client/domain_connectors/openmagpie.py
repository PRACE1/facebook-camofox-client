"""Adapter to wire into OpenMagpie."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, ClassVar

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_actions.runner import ActionRunner
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.search import GroupsSearchAction
from facebook_camofox_client.domain_posts.listen import PostsListenAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer


class FacebookCamofoxConnector:
    kind: ClassVar[str] = "facebook_search"

    def __init__(
        self,
        session_manager: Any | None = None,
        cursor_repo: Any | None = None,
        emitter: Any | None = None,
        normalizer: Any | None = None,
    ) -> None:
        # Dependencies are injectable for tests; production defaults are
        # unchanged from before (real Camofox session manager, in-memory
        # cursor repo/emitter, real normalizer).
        self.runner = ActionRunner()
        self.session_manager = session_manager or CamofoxSessionManager()
        self.cursor_repo = cursor_repo or InMemoryCursorRepository()
        self.emitter = emitter or InMemoryEventEmitter()
        self.normalizer = normalizer or PostNormalizer()

        search = GroupsSearchAction(self.session_manager, self.cursor_repo, self.normalizer, self.emitter)
        self.runner.register("groups.search", search.execute)

        listen = PostsListenAction(self.session_manager, self.cursor_repo, self.normalizer, self.emitter)
        self.runner.register("posts.listen", listen.execute)

    async def poll(self, spec: dict, since: datetime | None = None) -> Iterator[dict]:
        """groups.search boundary. Semantics unchanged from before posts.listen existed."""
        envelope = ActionEnvelope(
            action_id=f"poll-{datetime.now().timestamp()}",
            action_type="groups.search",
            account_id=spec.get("account_id", "default"),
            input=spec,
            idempotency_key=f"poll-{spec.get('page_url', '')}-{since}",
        )
        result = await self.runner.run(envelope)
        for record in result.get("results", []):
            yield record

    async def listen(self, spec: dict) -> Iterator[dict]:
        """posts.listen boundary. Separate action, separate cursor scope,
        driven entirely by the persisted watermark -- not by groups.search
        state or by anything held in memory across calls."""
        envelope = ActionEnvelope(
            action_id=f"listen-{datetime.now().timestamp()}",
            action_type="posts.listen",
            account_id=spec.get("account_id", "default"),
            input=spec,
            idempotency_key=f"listen-{spec.get('group_id', '')}",
        )
        result = await self.runner.run(envelope)
        for record in result.new_posts:
            yield record
