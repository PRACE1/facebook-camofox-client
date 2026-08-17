"""Smoke test for first vertical slice."""
import sys
sys.path.insert(0, "src")

import asyncio
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.search import GroupsSearchAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer

async def main():
    print("=== Smoke Test ===")
    session_mgr = CamofoxSessionManager()
    cursor_repo = InMemoryCursorRepository()
    emitter = InMemoryEventEmitter()
    normalizer = PostNormalizer()
    action = GroupsSearchAction(session_mgr, cursor_repo, normalizer, emitter)
    envelope = ActionEnvelope(
        action_id="s1",
        action_type="groups.search",
        account_id="demo",
        input={"group_ids": ["demo"], "terms": ["test"], "limit": 3},
        idempotency_key="sk1"
    )
    try:
        result = await action.execute(envelope)
        print(f"Results: {len(result.results)}")
    except Exception as e:
        print(f"Expected error without Camofox: {e}")
    print(f"Events: {len(emitter.events)}")
    for ev in emitter.events:
        print(f"  - {ev.event_type}")

if __name__ == "__main__":
    asyncio.run(main())
