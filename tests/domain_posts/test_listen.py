import asyncio
import pytest
from datetime import datetime, timezone

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_posts.listen import PostsListenAction
from facebook_camofox_client.domain_posts.schemas import PostsListenOutput


async def _fake_commit(_):
    return True


def make_normalizer():
    class FakeNormalizer:
        def normalize(self, raw, account_id, source_action, expected_group_id=None):
            from facebook_camofox_client.domain_records.models import NormalizedPostRecord
            post = raw
            return NormalizedPostRecord(
                account_id=account_id,
                record_id=f"rec-{post['post_id']}",
                record_type="facebook_post",
                external_id=post["post_id"],
                group_id=post.get("group_id", "305056891435827"),
                content=post.get("content") or post.get("text", ""),
                permalink=post.get("permalink", ""),
                occurred_at=post.get("occurred_at") or datetime.now(timezone.utc),
                author_name=post.get("author_name"),
                author_id=post.get("author_id"),
                raw_extraction={"source": "test"},
            )
    return FakeNormalizer()


@pytest.fixture
def deps():
    return {
        "session_manager": None,
        "cursor_repo": InMemoryCursorRepository(),
        "normalizer": make_normalizer(),
        "emitter": InMemoryEventEmitter(),
    }


@pytest.mark.asyncio
async def test_first_poll_emits_all_new_posts_and_advances_cursor(deps):
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
                    {"post_id": "1", "text": "hello", "occurred_at": "2026-08-21T12:00:00+00:00"},
                    {"post_id": "2", "text": "world", "occurred_at": "2026-08-21T12:01:00+00:00"},
                ],
                "counters": {"scroll_phase_dropped": 0},
                "degraded": False,
            }

    class FakeManager:
        async def acquire(self, account_id, **kwargs): return FakeSession()
        async def release(self, session): pass

    action = PostsListenAction(
        FakeManager(), deps["cursor_repo"], deps["normalizer"], deps["emitter"],
        commit=_fake_commit,
    )

    envelope = ActionEnvelope(
        action_id="test-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-1",
    )

    result = await action.execute(envelope)
    assert len(result.new_posts) == 2
    assert result.cursor_advanced is True


@pytest.mark.asyncio
async def test_reconnect_replay_skips_already_seen_posts(deps):
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
                    {"post_id": "1", "text": "hello", "occurred_at": "2026-08-21T12:00:00+00:00"},
                    {"post_id": "2", "text": "world", "occurred_at": "2026-08-21T12:01:00+00:00"},
                ],
                "counters": {"scroll_phase_dropped": 0},
                "degraded": False,
            }

    class FakeManager:
        async def acquire(self, account_id, **kwargs): return FakeSession()
        async def release(self, session): pass

    action = PostsListenAction(
        FakeManager(), deps["cursor_repo"], deps["normalizer"], deps["emitter"],
        commit=_fake_commit,
    )

    envelope1 = ActionEnvelope(
        action_id="test-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-1",
    )
    await action.execute(envelope1)

    envelope2 = ActionEnvelope(
        action_id="test-2",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-2",
    )
    result2 = await action.execute(envelope2)
    assert result2.new_posts == []
    assert result2.cursor_advanced is False


@pytest.mark.asyncio
async def test_no_new_posts_since_last_poll_does_not_advance_cursor(deps):
    class FakeSession:
        async def open_surface(self, surface, target):
            class Page:
                async def title(self): return "Test Group"
                @property
                def url(self): return "https://web.facebook.com/groups/305056891435827"
            return Page()

        async def execute(self, activity, params):
            return {
                "results": [],
                "counters": {"scroll_phase_dropped": 0},
                "degraded": False,
            }

    class FakeManager:
        async def acquire(self, account_id, **kwargs): return FakeSession()
        async def release(self, session): pass

    action = PostsListenAction(
        FakeManager(), deps["cursor_repo"], deps["normalizer"], deps["emitter"],
        commit=_fake_commit,
    )

    envelope = ActionEnvelope(
        action_id="test-1",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-1",
    )

    result = await action.execute(envelope)
    assert result.new_posts == []
    assert result.cursor_advanced is False


@pytest.mark.asyncio
async def test_auth_expired_fails_loudly_and_leaves_cursor_untouched(deps):
    class FakeSession:
        async def open_surface(self, surface, target):
            class Page:
                async def title(self): return "Log in to Facebook"
                @property
                def url(self): return "https://web.facebook.com/login"
            return Page()

    class FakeManager:
        async def acquire(self, account_id, **kwargs): return FakeSession()
        async def release(self, session): pass

    action = PostsListenAction(
        FakeManager(), deps["cursor_repo"], deps["normalizer"], deps["emitter"],
        commit=_fake_commit,
    )

    envelope = ActionEnvelope(
        action_id="test-auth",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-auth",
    )

    result = await action.execute(envelope)
    assert result.new_posts == []
    assert result.cursor_advanced is False


@pytest.mark.asyncio
async def test_dropped_scroll_responses_mark_poll_degraded_even_with_new_posts(deps):
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
                    {"post_id": "1", "text": "hello", "occurred_at": "2026-08-21T12:00:00+00:00"},
                ],
                "counters": {"scroll_phase_dropped": 2},
                "degraded": True,
            }

    class FakeManager:
        async def acquire(self, account_id, **kwargs): return FakeSession()
        async def release(self, session): pass

    action = PostsListenAction(
        FakeManager(), deps["cursor_repo"], deps["normalizer"], deps["emitter"],
        commit=_fake_commit,
    )

    envelope = ActionEnvelope(
        action_id="test-degraded",
        action_type="posts.listen",
        account_id="acc1",
        input={"group_id": "305056891435827", "terms": [], "limit": 3},
        idempotency_key="test-degraded",
    )

    result = await action.execute(envelope)
    assert len(result.new_posts) == 1
    assert result.cursor_advanced is True