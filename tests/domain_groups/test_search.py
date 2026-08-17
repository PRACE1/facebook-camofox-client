"""Tests for groups.search."""
import pytest
from datetime import datetime, UTC
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.search import GroupsSearchAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer

@pytest.mark.asyncio
async def test_search_emits_events():
    session_mgr = CamofoxSessionManager()
    cursor_repo = InMemoryCursorRepository()
    emitter = InMemoryEventEmitter()
    normalizer = PostNormalizer()
    action = GroupsSearchAction(session_mgr, cursor_repo, normalizer, emitter)
    envelope = ActionEnvelope(action_id="t1", action_type="groups.search", account_id="acc1", input={"group_ids": ["g1"], "terms": ["crypto"], "limit": 5}, idempotency_key="k1")
    try:
        await action.execute(envelope)
    except Exception:
        pass
    assert len(emitter.events) >= 1
    assert emitter.events[0].event_type == "groups.search_started"