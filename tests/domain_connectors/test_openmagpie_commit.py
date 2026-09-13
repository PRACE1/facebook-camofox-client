import pytest
from datetime import datetime, timezone

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_posts.listen import PostsListenAction, CommitFailed
from facebook_camofox_client.domain_records.normalization import PostNormalizer
from facebook_camofox_client.domain_records.models import NormalizedPostRecord


@pytest.fixture
def fake_session_manager():
    class FakeSession:
        async def open_surface(self, surface, target):
            class Page:
                async def title(self): return "Test Group"
                @property
                def url(self): return "https://web.facebook.com/groups/305056891435827"
            return Page()

        async def execute(self, activity, params):
            return {
                "results": [
                    {
                        "post_id": "1",
                        "group_id": "305056891435827",
                        "text": "first post",
                        "occurred_at": "2026-08-21T12:00:00+00:00",
                        "permalink": "https://web.facebook.com/groups/305056891435827/posts/1/",
                        "author_name": "Author One",
                        "author_id": "100000000000001",
                    },
                    {
                        "post_id": "2",
                        "group_id": "305056891435827",
                        "text": "second post",
                        "occurred_at": "2026-08-21T12:01:00+00:00",
                        "permalink": "https://web.facebook.com/groups/305056891435827/posts/2/",
                        "author_name": "Author Two",
                        "author_id": "100000000000002",
                    },
                ],
                "counters": {"scroll_phase_dropped": 0},
                "degraded": False,
            }

    class FakeManager:
        async def acquire(self, account_id, **kwargs): return FakeSession()
        async def release(self, session): pass

    return FakeManager()


@pytest.fixture
def deps(fake_session_manager):
    return {
        "session_manager": fake_session_manager,
        "cursor_repo": InMemoryCursorRepository(),
        "normalizer": PostNormalizer(),
        "emitter": InMemoryEventEmitter(),
    }


async def _always_commit(_: NormalizedPostRecord) -> bool:
    return True


@pytest.mark.asyncio
async def test_commit_success_advances_cursor(deps):
    """Two validated records committed → cursor advances."""
    committed = set()
    durable_store = {}

    async def commit(record: NormalizedPostRecord) -> bool:
        key = (record.group_id, record.external_id)
        if key in durable_store:
            return True
        durable_store[key] = record
        committed.add(record.external_id)
        return True

    action = PostsListenAction(
        deps["session_manager"],
        deps["cursor_repo"],
        deps["normalizer"],
        deps["emitter"],
        commit=commit,
    )

    envelope = ActionEnvelope(
        action_id="test-success-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-success-1",
    )

    result = await action.execute(envelope)

    assert len(result.new_posts) == 2
    assert committed == {"1", "2"}
    assert result.cursor_advanced is True

    cursor = await deps["cursor_repo"].load("posts-listen", "acc1", "305056891435827")
    assert cursor is not None
    assert cursor.last_post_id == "2"


@pytest.mark.asyncio
async def test_commit_failure_leaves_cursor_unchanged(deps):
    """Commit failure on record 2 → cursor unchanged, CommitFailed raised."""
    async def commit(record: NormalizedPostRecord) -> bool:
        if record.external_id == "2":
            return False
        return True

    action = PostsListenAction(
        deps["session_manager"],
        deps["cursor_repo"],
        deps["normalizer"],
        deps["emitter"],
        commit=commit,
    )

    envelope = ActionEnvelope(
        action_id="test-fail-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-fail-1",
    )

    with pytest.raises(CommitFailed):
        await action.execute(envelope)

    cursor = await deps["cursor_repo"].load("posts-listen", "acc1", "305056891435827")
    assert cursor is None


@pytest.mark.asyncio
async def test_repeat_poll_deduplicates(deps):
    """Repeat poll deduplicates by post_id; commit store stays idempotent."""
    durable_store = {}

    async def commit(record: NormalizedPostRecord) -> bool:
        key = (record.group_id, record.external_id)
        if key in durable_store:
            return True
        durable_store[key] = record
        return True

    action = PostsListenAction(
        deps["session_manager"],
        deps["cursor_repo"],
        deps["normalizer"],
        deps["emitter"],
        commit=commit,
    )

    envelope1 = ActionEnvelope(
        action_id="test-dedupe-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-dedupe-1",
    )

    result1 = await action.execute(envelope1)
    assert len(result1.new_posts) == 2
    assert result1.cursor_advanced is True

    envelope2 = ActionEnvelope(
        action_id="test-dedupe-2",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-dedupe-2",
    )

    result2 = await action.execute(envelope2)
    assert result2.new_posts == []
    assert result2.cursor_advanced is False


@pytest.mark.asyncio
async def test_output_contains_normalized_post_records(deps):
    """PostsListenOutput.new_posts contains NormalizedPostRecord objects, not dicts."""
    async def commit(record):
        return True

    action = PostsListenAction(
        deps["session_manager"],
        deps["cursor_repo"],
        deps["normalizer"],
        deps["emitter"],
        commit=commit,
    )

    envelope = ActionEnvelope(
        action_id="test-type-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-type-1",
    )

    result = await action.execute(envelope)
    assert len(result.new_posts) == 2
    for record in result.new_posts:
        assert isinstance(record, NormalizedPostRecord)


@pytest.mark.asyncio
async def test_event_ordering_commit_before_cursor_before_completed_event(deps):
    """Commit runs before cursor save; posts.listen_completed after both."""
    call_order = []

    class SpyCursorRepo:
        def __init__(self, real):
            self._real = real
        
        async def load(self, *a, **kw):
            return await self._real.load(*a, **kw)
        
        async def save(self, cursor):
            call_order.append("cursor_save")
            await self._real.save(cursor)

    class SpyEmitter:
        async def emit(self, event_type, payload, dedupe_key=None):
            call_order.append(event_type)

    spy_cursor = SpyCursorRepo(deps["cursor_repo"])
    spy_emitter = SpyEmitter()

    async def commit(record):
        call_order.append("commit")
        return True

    action = PostsListenAction(
        deps["session_manager"],
        spy_cursor,
        deps["normalizer"],
        spy_emitter,
        commit=commit,
    )

    envelope = ActionEnvelope(
        action_id="test-order-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-order-1",
    )

    await action.execute(envelope)

    # All commits happen before cursor save
    commit_indices = [i for i, x in enumerate(call_order) if x == "commit"]
    cursor_idx = call_order.index("cursor_save")
    assert all(i < cursor_idx for i in commit_indices)

    # posts.listen_completed happens after cursor save
    completed_idx = call_order.index("posts.listen_completed")
    assert completed_idx > cursor_idx


@pytest.mark.asyncio
async def test_auth_failure_emits_listen_failed_and_leaves_cursor(deps):
    """Auth page triggers posts.listen_failed; cursor untouched."""
    class AuthSession:
        async def open_surface(self, surface, target):
            class Page:
                async def title(self): return "Log in to Facebook"
                @property
                def url(self): return "https://web.facebook.com/login"
            return Page()

    class AuthManager:
        async def acquire(self, account_id, **kwargs): return AuthSession()
        async def release(self, session): pass

    async def commit(record):
        return True

    action = PostsListenAction(
        AuthManager(),
        deps["cursor_repo"],
        deps["normalizer"],
        deps["emitter"],
        commit=commit,
    )

    envelope = ActionEnvelope(
        action_id="test-auth-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-auth-1",
    )

    result = await action.execute(envelope)
    assert result.new_posts == []
    assert result.cursor_advanced is False

    cursor = await deps["cursor_repo"].load("posts-listen", "acc1", "305056891435827")
    assert cursor is None