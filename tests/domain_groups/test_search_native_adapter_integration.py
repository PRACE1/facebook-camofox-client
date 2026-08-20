"""Integration test: groups.search wired to NativeResponseAdapter.

Covers VIBE BOT's ask: a response containing two posts, one duplicate,
and one wrong-group record, asserting clean records reach result_found
exactly once each, and that scroll-phase drops mark the search degraded.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_groups.search import GroupsSearchAction


EXPECTED_GROUP_ID = "999"


def make_post_json(post_id, group_id, name, uid, ts, text):
    # Real Facebook Relay payloads have tens of thousands of characters of
    # unrelated attachment/styling data between records. Pad here so the
    # windowed extraction in extract_from_relay can't bleed into a
    # neighboring post's fields (min window bound is 1500 chars).
    filler = '"unrelated_filler":"' + ("x" * 2000) + '",'
    return (
        '{"post_id":"%s","associated_group":{"context_actor_hovercard":"GROUP","id":"%s"},'
        '"creation_time":%d,"owning_profile":{"__typename":"User","name":"%s","id":"%s"},'
        '"message":{"text":"%s"},%s"trailing_padding":"' + ("y" * 2000) + '"}'
    ) % (post_id, group_id, ts, name, uid, text, filler)


class FakeResponse:
    def __init__(self, body_bytes, status=200):
        self.status = status
        self.headers = {"content-type": "application/json"}
        self._body = body_bytes

    async def body(self):
        return self._body


class FakePage:
    def __init__(self):
        self.url = f"https://web.facebook.com/groups/{EXPECTED_GROUP_ID}"
        self._handlers = {}

    def on(self, event, handler):
        self._handlers[event] = handler

    async def goto(self, url, wait_until=None):
        pass

    async def wait_for_timeout(self, ms):
        pass

    async def content(self):
        # no page-load Relay records; everything comes via network responses
        return "<html></html>"

    async def evaluate(self, script):
        # simulate the page firing a network response on each "scroll"
        handler = self._handlers.get("response")
        if handler:
            post_a = make_post_json("100", EXPECTED_GROUP_ID, "Alice", "1", 1786999800, "Post A")
            post_b = make_post_json("200", EXPECTED_GROUP_ID, "Bob", "2", 1786999900, "Post B")
            duplicate_of_a = make_post_json("100", EXPECTED_GROUP_ID, "Alice", "1", 1786999800, "Post A")
            wrong_group = make_post_json("300", "111111111", "Carol", "3", 1787000000, "Wrong group")
            body = f'[{post_a},{post_b},{duplicate_of_a},{wrong_group}]'
            handler(FakeResponse(body.encode("utf-8")))

    async def title(self):
        return "Test Group | Facebook"


class FakeContext:
    def __init__(self, page):
        self._page = page

    async def new_page(self):
        return self._page

    async def close(self):
        pass


class FakeRuntime:
    async def __aexit__(self, *a):
        pass


class FakeSession:
    """Real CamofoxSession-shaped object, but with fake page/context."""
    def __init__(self, context):
        self.context = context
        self._closed = False

    async def open_surface(self, surface, target):
        if surface != "facebook_group":
            raise ValueError(f"unsupported surface: {surface}")
        page = await self.context.new_page()
        return page

    async def execute(self, activity, params):
        from facebook_camofox_client.domain_camofox.session_manager import CamofoxSession
        real_session = CamofoxSession(
            account_id="acc1", runtime=FakeRuntime(), browser=None, context=self.context
        )
        return await real_session.execute(activity, params)


class FakeSessionManager:
    def __init__(self, session):
        self._session = session
        self.release_count = 0

    async def acquire(self, account_id, proxy_config=None):
        return self._session

    async def release(self, session):
        self.release_count += 1


def make_envelope():
    return ActionEnvelope(
        action_id="native-int-1",
        action_type="groups.search",
        account_id="acc1",
        input={"group_ids": [EXPECTED_GROUP_ID], "terms": [], "limit": 2},
        idempotency_key="native-int-k1"
    )


@pytest.mark.asyncio
async def test_clean_records_reach_result_found_exactly_once_each():
    page = FakePage()
    context = FakeContext(page)
    session = FakeSession(context)
    mgr = FakeSessionManager(session)

    mock_normalizer = MagicMock()
    call_count = {"n": 0}
    def fake_normalize(raw, account_id, source_action):
        call_count["n"] += 1
        rec = MagicMock()
        rec.record_id = f"rec-{raw.get('post_id') or raw.post_id}"
        rec.model_dump.return_value = {"record_id": rec.record_id}
        return rec
    mock_normalizer.normalize.side_effect = fake_normalize

    mock_emitter = AsyncMock()
    mock_cursor_repo = MagicMock()

    action = GroupsSearchAction(mgr, mock_cursor_repo, mock_normalizer, mock_emitter)
    result = await action.execute(make_envelope())

    # two clean, distinct posts should each hit normalize exactly once
    assert call_count["n"] == 2

    result_found_events = [
        c for c in mock_emitter.emit.await_args_list if c.args[0] == "groups.result_found"
    ]
    assert len(result_found_events) == 2

    # no duplicate re-emitted, wrong-group excluded
    record_ids_emitted = {c.args[1]["record_id"] for c in result_found_events}
    assert len(record_ids_emitted) == 2


@pytest.mark.asyncio
async def test_scroll_phase_drops_mark_search_degraded():
    """If NativeResponseAdapter reports scroll-phase drops, the search
    result must be marked degraded, not reported as clean coverage."""
    from facebook_camofox_client.domain_extraction.response_capture import NativeResponseAdapter

    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)
    adapter._queue = __import__("asyncio").Queue(maxsize=1)
    resp = FakeResponse(body_bytes=b'{}')

    adapter.mark_scroll_started()
    adapter._on_response(resp)  # fills queue
    adapter._on_response(resp)  # dropped during scroll phase

    assert adapter.has_scroll_phase_drops is True
    assert adapter.counters["scroll_phase_dropped"] == 1