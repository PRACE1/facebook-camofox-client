from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_posts.listen import PostsListenAction
from facebook_camofox_client.domain_records.models import NormalizedPostRecord
from facebook_camofox_client.domain_records.normalization import PostNormalizer
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager


CommitCallback = Callable[[NormalizedPostRecord], Awaitable[bool]]


async def _missing_commit(_: NormalizedPostRecord) -> bool:
    raise RuntimeError(
        "posts.listen requires a durable commit(payload) callback before cursor advancement"
    )


class FacebookCamofoxConnector:
    def __init__(
        self,
        session_manager: Any | None = None,
        cursor_repo: Any | None = None,
        emitter: Any | None = None,
        normalizer: Any | None = None,
        commit: CommitCallback | None = None,
    ) -> None:
        self.session_manager = session_manager or CamofoxSessionManager()
        self.cursor_repo = cursor_repo or InMemoryCursorRepository()
        self.emitter = emitter or InMemoryEventEmitter()
        self.normalizer = normalizer or PostNormalizer()
        self.commit = commit or _missing_commit

    async def poll(self, spec: dict, since: datetime | None = None) -> AsyncIterator[dict]:
        listen = PostsListenAction(
            self.session_manager,
            self.cursor_repo,
            self.normalizer,
            self.emitter,
            commit=self.commit,
        )
        envelope = ActionEnvelope(
            action_id=f"poll-{datetime.utcnow().isoformat()}",
            action_type="posts.listen",
            account_id=spec.get("account_id", "default"),
            input=spec,
            idempotency_key=f"poll-{datetime.utcnow().isoformat()}",
        )
        result = await listen.execute(envelope)
        for post in result.new_posts:
            yield post.dict()

    async def listen(self, spec: dict) -> AsyncIterator[dict]:
        async for record in self.poll(spec):
            yield record