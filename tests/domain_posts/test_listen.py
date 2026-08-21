"""Fixture tests for posts.listen: new posts, duplicates across polls,
reconnect-safe cursor replay, auth/session expiry, and dropped scroll
responses correctly marking the poll degraded.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_posts.listen import PostsListenAction

GROUP_ID = "999"


class FakePage:
    def __init__(self, title="Test Group | Facebook", url=None):
        self._title = title
        self.url = url or f"https://web.facebook.com/groups/{GROUP_ID}"

    async def title(self):
        return self._title


class FakeSession:
    """Directly returns canned raw_results -- the adapter/session wiring
    itself is already covered elsewhere; this isolates cursor/dedup/
    failure logic in PostsListenAction."""

    def __init__(self, page, raw_results):
        self._page = page
        self._raw_results = raw_results

    async def open_surface(self, surface, target):
        return self._page

    async def execute(self, activity, params):
        return self._raw_results


class FakeSessionManager:
    def __init__(self, sessions):
        self._sessions = list(sessions)
        self.release_count = 0

    async def acquire(self, account_id, proxy_config=None):
        return self._sessions.pop(0)

    async def release(self, session):
        self.release_count += 1


def make_envelope(action_id="listen-1"):
    return ActionEnvelope(
        action_id=action_id,
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": GROUP_ID, "terms": [], "limit": 20},
        idempotency_key=f"{action_id}-k",
    )


def make_normalizer():
    normalizer = MagicMock()
    def fake_normalize(raw, account_id, source_action):
        rec = MagicMock()
        rec.record_id = f"rec-{raw.get('post_id')}"
        rec.model_dump.return_value = {"record_id": rec.record_id, "post_id": raw.get("post_id")}
        return rec
    normalizer.normalize.side_effect = fake_normalize
    return normalizer


@pytest.mark.asyncio
async def test_first_poll_emits_all_new_posts_and_advances_cursor():
    raw = {
        "results": [
            {"post_id": "1", "text": "first post", "created_at": "2026-08-20T10:00:00+00:00"},
            {"post_id": "2", "text": "second post", "created_at": "2026-08-20T10:05:00+00:00"},
        ],
        "counters": {"scroll_phase_dropped": 0},
    }
    mgr = FakeSessionManager([FakeSession(FakePage(), raw)])
    emitter = AsyncMock()
    cursor_repo = InMemoryCursorRepository()
    action = PostsListenAction(mgr, cursor_repo, make_normalizer(), emitter)

    result = await action.execute(make_envelope())

    assert len(result.new_posts) == 2
    assert result.cursor_advanced is True

    new_events = [c for c in emitter.emit.await_args_list if c.args[0] == "posts.new"]
    assert len(new_events) == 2

    saved_cursor = await cursor_repo.load("posts-listen", "acc1", GROUP_ID)
    assert saved_cursor.last_post_id == "2"


@pytest.mark.asyncio
async def test_reconnect_replay_skips_already_seen_posts():
    """Simulates a dropped connection: poll 1 sees posts 1 and 2. The
    connection drops and reconnects with a brand new session, which
    re-extracts posts 1, 2 (same as before) plus a genuinely new post 3.
    Only post 3 should emit posts.new."""
    raw_poll_1 = {
        "results": [
            {"post_id": "1", "text": "first post", "created_at": "2026-08-20T10:00:00+00:00"},
            {"post_id": "2", "text": "second post", "created_at": "2026-08-20T10:05:00+00:00"},
        ],
        "counters": {"scroll_phase_dropped": 0},
    }
    raw_poll_2_after_reconnect = {
        "results": [
            {"post_id": "1", "text": "first post", "created_at": "2026-08-20T10:00:00+00:00"},
            {"post_id": "2", "text": "second post", "created_at": "2026-08-20T10:05:00+00:00"},
            {"post_id": "3", "text": "third post, arrived after reconnect", "created_at": "2026-08-20T10:10:00+00:00"},
        ],
        "counters": {"scroll_phase_dropped": 0},
    }

    cursor_repo = InMemoryCursorRepository()
    normalizer = make_normalizer()

    mgr1 = FakeSessionManager([FakeSession(FakePage(), raw_poll_1)])
    action1 = PostsListenAction(mgr1, cursor_repo, normalizer, AsyncMock())
    result1 = await action1.execute(make_envelope("listen-1"))
    assert len(result1.new_posts) == 2

    emitter2 = AsyncMock()
    mgr2 = FakeSessionManager([FakeSession(FakePage(), raw_poll_2_after_reconnect)])
    action2 = PostsListenAction(mgr2, cursor_repo, normalizer, emitter2)
    result2 = await action2.execute(make_envelope("listen-2"))

    assert len(result2.new_posts) == 1
    assert result2.new_posts[0]["post_id"] == "3"

    new_events_2 = [c for c in emitter2.emit.await_args_list if c.args[0] == "posts.new"]
    assert len(new_events_2) == 1
    assert result2.cursor_advanced is True


@pytest.mark.asyncio
async def test_no_new_posts_since_last_poll_does_not_advance_cursor():
    raw = {
        "results": [
            {"post_id": "1", "text": "first post", "created_at": "2026-08-20T10:00:00+00:00"},
        ],
        "counters": {"scroll_phase_dropped": 0},
    }
    cursor_repo = InMemoryCursorRepository()
    normalizer = make_normalizer()

    mgr1 = FakeSessionManager([FakeSession(FakePage(), raw)])
    action1 = PostsListenAction(mgr1, cursor_repo, normalizer, AsyncMock())
    await action1.execute(make_envelope("listen-1"))

    mgr2 = FakeSessionManager([FakeSession(FakePage(), raw)])
    emitter2 = AsyncMock()
    action2 = PostsListenAction(mgr2, cursor_repo, normalizer, emitter2)
    result2 = await action2.execute(make_envelope("listen-2"))

    assert len(result2.new_posts) == 0
    assert result2.cursor_advanced is False
    new_events = [c for c in emitter2.emit.await_args_list if c.args[0] == "posts.new"]
    assert len(new_events) == 0


@pytest.mark.asyncio
async def test_auth_expired_fails_loudly_and_leaves_cursor_untouched():
    raw = {"results": [], "counters": {}}
    cursor_repo = InMemoryCursorRepository()
    normalizer = make_normalizer()

    mgr1 = FakeSessionManager([FakeSession(
        FakePage(),
        {"results": [{"post_id": "1", "text": "seed post", "created_at": "2026-08-20T10:00:00+00:00"}],
         "counters": {"scroll_phase_dropped": 0}},
    )])
    await PostsListenAction(mgr1, cursor_repo, normalizer, AsyncMock()).execute(make_envelope("listen-1"))
    cursor_before = await cursor_repo.load("posts-listen", "acc1", GROUP_ID)

    login_page = FakePage(title="Log In to Facebook", url="https://web.facebook.com/login")
    mgr2 = FakeSessionManager([FakeSession(login_page, raw)])
    emitter2 = AsyncMock()
    action2 = PostsListenAction(mgr2, cursor_repo, normalizer, emitter2)
    result2 = await action2.execute(make_envelope("listen-2"))

    assert result2.new_posts == []
    assert result2.cursor_advanced is False

    failed_events = [c for c in emitter2.emit.await_args_list if c.args[0] == "posts.listen_failed"]
    assert len(failed_events) == 1
    assert failed_events[0].args[1]["reason"] == "auth_required"

    cursor_after = await cursor_repo.load("posts-listen", "acc1", GROUP_ID)
    assert cursor_after.last_post_id == cursor_before.last_post_id
    assert cursor_after.watermark == cursor_before.watermark

    assert mgr2.release_count == 1


@pytest.mark.asyncio
async def test_dropped_scroll_responses_mark_poll_degraded_even_with_new_posts():
    raw = {
        "results": [
            {"post_id": "1", "text": "a real new post", "created_at": "2026-08-20T10:00:00+00:00"},
        ],
        "counters": {"scroll_phase_dropped": 3},
    }
    cursor_repo = InMemoryCursorRepository()
    emitter = AsyncMock()
    mgr = FakeSessionManager([FakeSession(FakePage(), raw)])
    action = PostsListenAction(mgr, cursor_repo, make_normalizer(), emitter)

    result = await action.execute(make_envelope())

    assert len(result.new_posts) == 1

    completed_events = [c for c in emitter.emit.await_args_list if c.args[0] == "posts.listen_completed"]
    assert len(completed_events) == 1
    assert completed_events[0].args[1]["degraded"] is True
    assert completed_events[0].args[1]["scroll_phase_dropped"] == 3
