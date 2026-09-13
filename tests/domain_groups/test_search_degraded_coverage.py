"""Integration test per VIBE BOT review: scroll_phase_dropped > 0 must
mark the search degraded, not silently report clean coverage."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_groups.search import GroupsSearchAction


@pytest.mark.asyncio
async def test_scroll_phase_drops_mark_search_degraded_not_clean():
    mock_page = AsyncMock()
    mock_page.title.return_value = "Test Group | Facebook"
    mock_page.url = "https://web.facebook.com/groups/999"

    mock_session = AsyncMock()
    mock_session.open_surface.return_value = mock_page
    mock_session.execute.return_value = {
        "results": [
            {"post_id": "1", "group_id": "999", "author_name": "Alice", "author_id": "1",
             "text": "Clean post", "created_at": "2026-08-20T12:00:00+00:00",
             "permalink": "https://web.facebook.com/groups/999/posts/1/",
             "collected_at": "2026-08-20T12:00:00+00:00", "source": "relay"},
        ],
        "warning": "2 response(s) dropped during scroll phase",
        "failure_reason": None,
        # This is the key signal: even though we got a clean record,
        # coverage during the scroll was NOT complete.
        "counters": {
            "responses_seen": 50, "json_responses": 5, "candidate_records": 1,
            "accepted": 1, "duplicates": 0, "rejected": 0,
            "prelaunch_dropped": 0, "scroll_phase_dropped": 2,
        },
    }

    mock_session_manager = AsyncMock()
    mock_session_manager.acquire.return_value = mock_session

    mock_normalizer = MagicMock()
    mock_record = MagicMock()
    mock_record.record_id = "rec-1"
    mock_record.model_dump.return_value = {"record_id": "rec-1", "content": "Clean post"}
    mock_normalizer.normalize.return_value = mock_record

    mock_emitter = AsyncMock()
    mock_cursor_repo = MagicMock()

    action = GroupsSearchAction(mock_session_manager, mock_cursor_repo, mock_normalizer, mock_emitter)
    envelope = ActionEnvelope(
        action_id="test-drops-1",
        action_type="groups.search",
        account_id="test-account",
        input={"group_ids": ["999"], "terms": [], "limit": 3},
        idempotency_key="test-drops-k1"
    )

    result = await action.execute(envelope)

    # The clean record still reaches result_found exactly once.
    assert len(result.results) == 1
    result_found_events = [c for c in mock_emitter.emit.await_args_list if c.args[0] == "groups.result_found"]
    assert len(result_found_events) == 1

    # But the completed event must NOT claim clean coverage.
    completed_events = [c for c in mock_emitter.emit.await_args_list if c.args[0] == "groups.search_completed"]
    assert len(completed_events) == 1
    payload = completed_events[0].args[1]
    assert payload["records_found"] == 1
    assert payload["scroll_phase_dropped"] == 2
    assert payload["degraded"] is True  # this is the assertion that matters
