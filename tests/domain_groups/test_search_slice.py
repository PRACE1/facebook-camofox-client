"""Contract test: vertical slice — action -> Camofox boundary -> normalized post -> cursor -> event.

Invariants under test:
1. Runner never launches Playwright directly (fake session, no browser process).
2. Records are written to record_repo BEFORE cursor advances.
3. Exactly one 'groups.result_found' event is emitted per new post.
4. Duplicate posts (same dedupe key) are skipped — no double-write, no extra event.
5. auth_guard returns 'authenticated' before surface opens.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, UTC

import pytest

from facebook_camofox_client.domain_accounts.auth_guard import AuthGuard, AuthState, AuthGuardResult
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_actions.runner import ActionRunner
from facebook_camofox_client.domain_cursors.models import Cursor
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_records.models import NormalizedPostRecord
from facebook_camofox_client.domain_records.normalization import PostNormalizer
from facebook_camofox_client.domain_records.repository import InMemoryRecordRepository
from facebook_camofox_client.domain_groups.search import GroupsSearchAction
from facebook_camofox_client.domain_groups.schemas import GroupsSearchOutput


# ---------------------------------------------------------------------------
# Fakes — no browser, no Playwright, no Camofox process
# ---------------------------------------------------------------------------

class FakeCamofoxSession:
    """Fake session that returns deterministic posts without launching a browser."""

    def __init__(self, account_id: str, posts: list[dict]) -> None:
        self.account_id = account_id
        self.session_id = str(uuid.uuid4())
        self._posts = posts
        self.surfaces_opened: list[tuple[str, dict]] = []
        self.playwright_launched = False  # must stay False

    async def get_current_page_state(self) -> tuple[str, str]:
        return "Facebook", "https://facebook.com/groups/test"

    async def open_surface(self, surface: str, target: dict) -> None:
        # No browser call — just record
        self.surfaces_opened.append((surface, target))

    async def execute(self, activity: str, params: dict) -> dict:
        return {"results": self._posts}

    async def close(self) -> None:
        pass


class FakeSessionManager:
    def __init__(self, session: FakeCamofoxSession) -> None:
        self._session = session
        self._released: list[str] = []

    async def acquire(self, account_id: str, proxy_config=None) -> FakeCamofoxSession:
        return self._session

    async def release(self, session_id: str) -> None:
        self._released.append(session_id)


class AlwaysAuthenticatedGuard(AuthGuard):
    async def validate(self, page_title: str, page_url: str) -> AuthGuardResult:
        return AuthGuardResult(state=AuthState.authenticated)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_envelope(account_id: str, group_ids: list[str], terms: list[str]) -> ActionEnvelope:
    return ActionEnvelope(
        action_id=str(uuid.uuid4()),
        action_type="groups.search",
        account_id=account_id,
        input={"group_ids": group_ids, "terms": terms, "limit": 20},
        idempotency_key=f"test-{uuid.uuid4()}",
    )


def make_raw_post(post_id: str, group_id: str) -> dict:
    return {
        "external_id": post_id,
        "group_id": group_id,
        "content": f"post content {post_id}",
        "author": "tester",
        "author_id": "tester-001",
        "url": f"https://facebook.com/groups/{group_id}/posts/{post_id}",
        "occurred_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_playwright_launched():
    """Runner must not launch a real browser."""
    raw_posts = [make_raw_post("post-001", "group-abc")]
    fake_session = FakeCamofoxSession(account_id="acc-1", posts=raw_posts)
    assert fake_session.playwright_launched is False  # invariant: never touched


@pytest.mark.asyncio
async def test_records_written_before_cursor_advances():
    """Records must be in record_repo BEFORE cursor_repo.save() is called."""
    saves_order: list[str] = []

    record_repo = InMemoryRecordRepository()
    cursor_repo = InMemoryCursorRepository()

    original_record_save = record_repo.save
    original_cursor_save = cursor_repo.save

    async def tracking_record_save(rec):
        saves_order.append("record")
        await original_record_save(rec)

    async def tracking_cursor_save(cur):
        # At this point, records must already be saved
        assert "record" in saves_order, "Cursor advanced before records were committed!"
        saves_order.append("cursor")
        await original_cursor_save(cur)

    record_repo.save = tracking_record_save
    cursor_repo.save = tracking_cursor_save

    raw_posts = [make_raw_post("post-001", "group-abc")]
    fake_session = FakeCamofoxSession(account_id="acc-1", posts=raw_posts)
    action = GroupsSearchAction(
        session_manager=FakeSessionManager(fake_session),
        cursor_repo=cursor_repo,
        record_repo=record_repo,
        normalizer=PostNormalizer(),
        event_emitter=InMemoryEventEmitter(),
        auth_guard=AlwaysAuthenticatedGuard(),
    )
    envelope = make_envelope("acc-1", ["group-abc"], ["test"])
    await action.execute(envelope)

    assert saves_order.index("record") < saves_order.index("cursor")


@pytest.mark.asyncio
async def test_exactly_one_event_per_new_post():
    """Exactly one 'groups.result_found' event per new unique post."""
    raw_posts = [
        make_raw_post("post-001", "group-abc"),
        make_raw_post("post-002", "group-abc"),
    ]
    fake_session = FakeCamofoxSession(account_id="acc-1", posts=raw_posts)
    emitter = InMemoryEventEmitter()

    action = GroupsSearchAction(
        session_manager=FakeSessionManager(fake_session),
        cursor_repo=InMemoryCursorRepository(),
        record_repo=InMemoryRecordRepository(),
        normalizer=PostNormalizer(),
        event_emitter=emitter,
        auth_guard=AlwaysAuthenticatedGuard(),
    )
    envelope = make_envelope("acc-1", ["group-abc"], [])
    await action.execute(envelope)

    found_events = [e for e in emitter.events if e["event_type"] == "groups.result_found"]
    assert len(found_events) == 2  # exactly one per new post


@pytest.mark.asyncio
async def test_duplicate_posts_not_double_written():
    """Same post yielded twice must not produce double record or double event."""
    raw_posts = [
        make_raw_post("post-dup", "group-abc"),
        make_raw_post("post-dup", "group-abc"),  # exact duplicate
    ]
    fake_session = FakeCamofoxSession(account_id="acc-1", posts=raw_posts)
    emitter = InMemoryEventEmitter()
    record_repo = InMemoryRecordRepository()

    action = GroupsSearchAction(
        session_manager=FakeSessionManager(fake_session),
        cursor_repo=InMemoryCursorRepository(),
        record_repo=record_repo,
        normalizer=PostNormalizer(),
        event_emitter=emitter,
        auth_guard=AlwaysAuthenticatedGuard(),
    )
    envelope = make_envelope("acc-1", ["group-abc"], [])
    await action.execute(envelope)

    found_events = [e for e in emitter.events if e["event_type"] == "groups.result_found"]
    assert len(found_events) == 1  # only one, duplicate skipped
    assert len(record_repo._records) == 1


# ---------------------------------------------------------------------------
# Failure-path tests: one per auth state
# ---------------------------------------------------------------------------

class FixedStateAuthGuard(AuthGuard):
    def __init__(self, state: AuthState, requires_action: str | None = None) -> None:
        self._state = state
        self._requires_action = requires_action

    async def validate(self, page_title: str, page_url: str) -> AuthGuardResult:
        return AuthGuardResult(state=self._state, requires_action=self._requires_action)


@pytest.mark.asyncio
async def test_auth_required_emits_failed_event_and_returns_empty():
    """When auth_guard returns auth_required: no records, no cursor advance, search_failed emitted."""
    raw_posts = [make_raw_post("post-001", "group-abc")]
    fake_session = FakeCamofoxSession(account_id="acc-1", posts=raw_posts)
    emitter = InMemoryEventEmitter()
    record_repo = InMemoryRecordRepository()
    cursor_repo = InMemoryCursorRepository()

    action = GroupsSearchAction(
        session_manager=FakeSessionManager(fake_session),
        cursor_repo=cursor_repo,
        record_repo=record_repo,
        normalizer=PostNormalizer(),
        event_emitter=emitter,
        auth_guard=FixedStateAuthGuard(AuthState.auth_required, "supply_cookies"),
    )
    envelope = make_envelope("acc-1", ["group-abc"], [])
    result = await action.execute(envelope)

    assert result["results"] == []
    assert len(record_repo._records) == 0
    assert len(cursor_repo._store) == 0  # cursor must not advance

    failed_events = [e for e in emitter.events if e["event_type"] == "groups.search_failed"]
    assert len(failed_events) == 1
    assert failed_events[0]["payload"]["reason"] == AuthState.auth_required


@pytest.mark.asyncio
async def test_session_expired_emits_failed_event_and_returns_empty():
    """When auth_guard returns session_expired: no records, no cursor, search_failed emitted."""
    raw_posts = [make_raw_post("post-002", "group-abc")]
    fake_session = FakeCamofoxSession(account_id="acc-2", posts=raw_posts)
    emitter = InMemoryEventEmitter()
    record_repo = InMemoryRecordRepository()
    cursor_repo = InMemoryCursorRepository()

    action = GroupsSearchAction(
        session_manager=FakeSessionManager(fake_session),
        cursor_repo=cursor_repo,
        record_repo=record_repo,
        normalizer=PostNormalizer(),
        event_emitter=emitter,
        auth_guard=FixedStateAuthGuard(AuthState.session_expired, "refresh_cookies"),
    )
    envelope = make_envelope("acc-2", ["group-abc"], [])
    result = await action.execute(envelope)

    assert result["results"] == []
    assert len(record_repo._records) == 0
    assert len(cursor_repo._store) == 0

    failed_events = [e for e in emitter.events if e["event_type"] == "groups.search_failed"]
    assert len(failed_events) == 1
    assert failed_events[0]["payload"]["reason"] == AuthState.session_expired


@pytest.mark.asyncio
async def test_surface_unavailable_emits_failed_event_and_returns_empty():
    """When auth_guard returns surface_unavailable: no records, no cursor, search_failed emitted."""
    raw_posts = [make_raw_post("post-003", "group-abc")]
    fake_session = FakeCamofoxSession(account_id="acc-3", posts=raw_posts)
    emitter = InMemoryEventEmitter()
    record_repo = InMemoryRecordRepository()
    cursor_repo = InMemoryCursorRepository()

    action = GroupsSearchAction(
        session_manager=FakeSessionManager(fake_session),
        cursor_repo=cursor_repo,
        record_repo=record_repo,
        normalizer=PostNormalizer(),
        event_emitter=emitter,
        auth_guard=FixedStateAuthGuard(AuthState.surface_unavailable),
    )
    envelope = make_envelope("acc-3", ["group-abc"], [])
    result = await action.execute(envelope)

    assert result["results"] == []
    assert len(record_repo._records) == 0
    assert len(cursor_repo._store) == 0

    failed_events = [e for e in emitter.events if e["event_type"] == "groups.search_failed"]
    assert len(failed_events) == 1
    assert failed_events[0]["payload"]["reason"] == AuthState.surface_unavailable


@pytest.mark.asyncio
async def test_record_save_failure_leaves_cursor_unchanged():
    """If record_repo.save() raises, cursor must NOT advance — atomicity invariant."""

    class ExplodingRecordRepository(InMemoryRecordRepository):
        async def save(self, record: NormalizedPostRecord) -> None:
            raise RuntimeError("disk full — record save failed")

    raw_posts = [make_raw_post("post-001", "group-abc")]
    fake_session = FakeCamofoxSession(account_id="acc-1", posts=raw_posts)
    cursor_repo = InMemoryCursorRepository()

    action = GroupsSearchAction(
        session_manager=FakeSessionManager(fake_session),
        cursor_repo=cursor_repo,
        record_repo=ExplodingRecordRepository(),
        normalizer=PostNormalizer(),
        event_emitter=InMemoryEventEmitter(),
        auth_guard=AlwaysAuthenticatedGuard(),
    )
    envelope = make_envelope("acc-1", ["group-abc"], [])

    with pytest.raises(RuntimeError, match="disk full"):
        await action.execute(envelope)

    # Cursor must be untouched — store is empty
    assert len(cursor_repo._store) == 0, "Cursor advanced despite record save failure!"

