import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_posts.listen import PostsListenAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer

GROUP_ID = os.environ["FACEBOOK_GROUP_ID"]
ACCOUNT_ID = os.environ.get("FACEBOOK_ACCOUNT_ID", "listen-group")
OUT = Path("tests/evidence/live_posts_listen_acceptance.json")


async def _accept_commit(_record) -> bool:
    """Durable commit stub for live acceptance — succeeds so cursor can advance."""
    return True


async def main():
    manager = CamofoxSessionManager()
    cursors = InMemoryCursorRepository()
    events = InMemoryEventEmitter()
    action = PostsListenAction(
        manager, cursors, PostNormalizer(), events, commit=_accept_commit
    )

    envelope = ActionEnvelope(
        action_id="live-posts-listen-acceptance-1",
        action_type="posts.listen",
        account_id=ACCOUNT_ID,
        input={"group_id": GROUP_ID, "terms": [], "limit": 3},
        idempotency_key="live-posts-listen-acceptance-1",
    )

    result = await action.execute(envelope)
    payload = {
        "mode": "live_unmocked",
        "group_id": GROUP_ID,
        "account_id": ACCOUNT_ID,
        "new_posts": result.model_dump(mode="json")["new_posts"],
        "cursor_advanced": result.cursor_advanced,
        "events": [
            {"event_type": e.event_type, "payload": e.payload}
            for e in events.events
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())