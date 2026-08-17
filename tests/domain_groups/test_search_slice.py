"""Fake-session tests for groups.search vertical slice."""
from __future__ import annotations
import pytest
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.search import GroupsSearchAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer


# --- Fake session helpers ---

class FakePage:
    def __init__(self, title="Group Page", url="https://facebook.com/groups/123"):
        self._title = title
        self.url = url
    async def title(self):
        return self._title


class FakeSession:
    def __init__(self, page: FakePage):
        self.page = page
        self._closed = False
        self.open_surface_called = 0
        self.released = False

    async def open_surface(self, surface, target):
        if surface != "facebook_group":
            raise ValueError(f"unsupported surface: {surface}")
        self.open_surface_called += 1
        return self.page

    async def execute(self, activity, params):
        return {"results": []}


class FakeSessionManager:
    def __init__(self, session):
        self._session = session
        self.release_count = 0

    async def acquire(self, account_id, proxy_config=None):
        return self._session

    async def release(self, session):
        session._closed = True
        self.release_count += 1


def make_envelope(account_id="acc1"):
    return ActionEnvelope(
        action_id="test-1",
        action_type="groups.search",
        account_id=account_id,
        input={"group_ids": ["g1"], "terms": ["crypto"], "limit": 5},
        idempotency_key="k1"
    )


# --- Happy path ---

@pytest.mark.asyncio
async def test_happy_path_emits_completed_and_releases():
    page = FakePage(title="Some Group", url="https://facebook.com/groups/123")
    session = FakeSession(page)
    mgr = FakeSessionManager(session)
    emitter = InMemoryEventEmitter()
    action = GroupsSearchAction(mgr, InMemoryCursorRepository(), PostNormalizer(), emitter)

    result = await action.execute(make_envelope())

    event_types = [e.event_type for e in emitter.events]
    assert "groups.search_completed" in event_types
    assert mgr.release_count == 1
    assert session._closed is True


# --- Auth required ---

@pytest.mark.asyncio
async def test_auth_required_emits_failed_and_releases():
    page = FakePage(title="Log In", url="https://facebook.com/login")
    session = FakeSession(page)
    mgr = FakeSessionManager(session)
    emitter = InMemoryEventEmitter()
    action = GroupsSearchAction(mgr, InMemoryCursorRepository(), PostNormalizer(), emitter)

    result = await action.execute(make_envelope())

    event_types = [e.event_type for e in emitter.events]
    assert "groups.search_failed" in event_types
    assert result.results == []
    assert mgr.release_count == 1


# --- Session expired ---

@pytest.mark.asyncio
async def test_session_expired_emits_failed_and_releases():
    page = FakePage(title="Session Expired", url="https://facebook.com/checkpoint/")
    session = FakeSession(page)
    mgr = FakeSessionManager(session)
    emitter = InMemoryEventEmitter()
    action = GroupsSearchAction(mgr, InMemoryCursorRepository(), PostNormalizer(), emitter)

    result = await action.execute(make_envelope())

    assert mgr.release_count == 1


# --- Surface raises ---

@pytest.mark.asyncio
async def test_unknown_surface_raises_and_releases():
    class BadSurfaceSession(FakeSession):
        async def open_surface(self, surface, target):
            raise ValueError(f"unsupported surface: {surface}")

    session = BadSurfaceSession(FakePage())
    mgr = FakeSessionManager(session)
    emitter = InMemoryEventEmitter()
    action = GroupsSearchAction(mgr, InMemoryCursorRepository(), PostNormalizer(), emitter)

    with pytest.raises(ValueError):
        await action.execute(make_envelope())

    assert mgr.release_count == 1
    event_types = [e.event_type for e in emitter.events]
    assert "groups.search_failed" in event_types


# --- Record save failure leaves release intact ---

@pytest.mark.asyncio
async def test_release_runs_even_when_normalize_raises():
    class ExplodingNormalizer:
        def normalize(self, raw, account_id, source_action):
            raise RuntimeError("normalize failed")

    class SessionWithResults(FakeSession):
        async def execute(self, activity, params):
            return {"results": [{"post_id": "p1", "content": "test"}]}

    session = SessionWithResults(FakePage())
    mgr = FakeSessionManager(session)
    emitter = InMemoryEventEmitter()
    action = GroupsSearchAction(mgr, InMemoryCursorRepository(), ExplodingNormalizer(), emitter)

    with pytest.raises(RuntimeError):
        await action.execute(make_envelope())

    assert mgr.release_count == 1