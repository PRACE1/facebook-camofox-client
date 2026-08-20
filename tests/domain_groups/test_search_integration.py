"""Integration test: groups.search returns normalized posts via fake session."""
import pytest
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.search import GroupsSearchAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer


class FakePage:
    def __init__(self):
        self.url = "https://facebook.com/groups/123"
    async def title(self):
        return "Test Group"
    async def evaluate(self, *args):
        pass
    async def wait_for_timeout(self, ms):
        pass


class FakeSession:
    def __init__(self):
        self._closed = False

    async def open_surface(self, surface, target):
        if surface != "facebook_group":
            raise ValueError(f"unsupported surface: {surface}")
        return FakePage()

    async def execute(self, activity, params):
        if activity != "facebook_group_search":
            raise NotImplementedError(f"unsupported activity: {activity}")
        return {"results": [
            {"post_id": "p1", "text": "crypto launch today", "author": "Alice",
             "author_id": "alice1", "url": "https://facebook.com/posts/p1",
             "likes": 10, "comments": 3, "shares": 1, "source": "relay"},
        ]}


class FakeSessionManager:
    def __init__(self):
        self.release_count = 0

    async def acquire(self, account_id, proxy_config=None):
        return FakeSession()

    async def release(self, session):
        session._closed = True
        self.release_count += 1


def make_envelope():
    return ActionEnvelope(
        action_id="int-1",
        action_type="groups.search",
        account_id="acc1",
        input={"group_ids": ["123"], "terms": ["crypto"], "limit": 5},
        idempotency_key="int-k1"
    )


@pytest.mark.asyncio
async def test_groups_search_returns_normalized_posts():
    mgr = FakeSessionManager()
    emitter = InMemoryEventEmitter()
    action = GroupsSearchAction(mgr, InMemoryCursorRepository(), PostNormalizer(), emitter)

    result = await action.execute(make_envelope())

    assert len(result.results) == 1
    rec = result.results[0]
    assert rec["external_id"] == "p1"
    assert rec["content"] == "crypto launch today"
    assert rec["metrics"]["likes"] == 10
    assert rec["account_id"] == "acc1"

    event_types = [e.event_type for e in emitter.events]
    assert "groups.result_found" in event_types
    assert "groups.search_completed" in event_types
    assert mgr.release_count == 1


@pytest.mark.asyncio
async def test_unsupported_activity_raises():
    session = FakeSession()
    with pytest.raises(NotImplementedError):
        await session.execute("unknown_activity", {})


from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_degraded_dom_fallbacks_excluded_from_clean_results():
    mock_page = AsyncMock()
    mock_page.title.return_value = "Test Group | Facebook"
    mock_page.url = "https://web.facebook.com/groups/999"
    mock_session = AsyncMock()
    mock_session.open_surface.return_value = mock_page
    mock_session.execute.return_value = {
        "results": [
            {"post_id": "111", "group_id": "999", "author_name": "Alice", "author_id": "1", "text": "Clean post text", "created_at": "2026-08-20T12:00:00+00:00", "permalink": "https://web.facebook.com/groups/999/posts/111/", "collected_at": "2026-08-20T12:00:00+00:00", "source": "relay"},
            {"post_id": "dom-unresolved-0", "group_id": "999", "author_name": None, "author_id": None, "text": "", "created_at": None, "permalink": "", "collected_at": "2026-08-20T12:00:00+00:00", "source": "dom"},
            {"post_id": "dom-unresolved-1", "group_id": "999", "author_name": None, "author_id": None, "text": None, "created_at": None, "permalink": "", "collected_at": "2026-08-20T12:00:00+00:00", "source": "dom"}
        ],
        "warning": "DOM fallback used",
        "failure_reason": None
    }
    mock_session_manager = AsyncMock()
    mock_session_manager.acquire.return_value = mock_session
    mock_normalizer = MagicMock()
    mock_record = MagicMock()
    mock_record.record_id = "rec-111"
    mock_record.model_dump.return_value = {"record_id": "rec-111", "text": "Clean post text"}
    mock_normalizer.normalize.return_value = mock_record
    mock_emitter = AsyncMock()
    mock_cursor_repo = MagicMock()
    action = GroupsSearchAction(mock_session_manager, mock_cursor_repo, mock_normalizer, mock_emitter)
    envelope = ActionEnvelope(
        action_id="test-1",
        action_type="groups.search",
        account_id="test-account",
        input={"group_ids": ["999"], "terms": [], "limit": 3},
        idempotency_key="test-k1"
    )
    result = await action.execute(envelope)
    assert len(result.results) == 1
    assert result.results[0]["record_id"] == "rec-111"
    assert mock_normalizer.normalize.call_count == 1
    result_found_events = [c for c in mock_emitter.emit.await_args_list if c.args[0] == "groups.result_found"]
    assert len(result_found_events) == 1
    completed_events = [c for c in mock_emitter.emit.await_args_list if c.args[0] == "groups.search_completed"]
    assert len(completed_events) == 1
    assert completed_events[0].args[1]["records_found"] == 1
    assert completed_events[0].args[1]["degraded_count"] == 2
