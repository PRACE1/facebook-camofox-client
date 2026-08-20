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
            {"post_id": "p1", "content": "crypto launch today", "author": "Alice",
             "author_id": "alice1", "url": "https://facebook.com/posts/p1",
             "likes": 10, "comments": 3, "shares": 1},
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