"""Fixture suite for NativeResponseAdapter.

Seven scenarios per review: valid response, mixed ads/reactions,
duplicate post across responses, malformed JSON, schema drift, wrong
group, response body read failure.

All payloads are structurally faithful but redacted — no real member
names or raw captured bodies, per review guidance.
"""
from __future__ import annotations

import pytest

from facebook_camofox_client.domain_extraction.response_capture import NativeResponseAdapter

EXPECTED_GROUP_ID = "305056891435827"


class FakeResponse:
    """Minimal stand-in for a Playwright Response object."""

    def __init__(self, status: int = 200, content_type: str = "application/json",
                 body_bytes: bytes | None = None, body_error: Exception | None = None):
        self.status = status
        self.headers = {"content-type": content_type}
        self._body_bytes = body_bytes or b""
        self._body_error = body_error

    async def body(self) -> bytes:
        if self._body_error is not None:
            raise self._body_error
        return self._body_bytes


def make_post_json(post_id: str, group_id: str, name: str, uid: str,
                    creation_time: int, message: str | None = None) -> str:
    """Build a structurally faithful (redacted) fragment matching the
    REAL schema field order found in production fixtures:
    feedback/associated_group BEFORE post_id, creation_time immediately
    AFTER post_id."""
    message_part = f',"message":{{"text":"{message}"}}' if message is not None else ""
    return (
        f'{{"feedback":{{"associated_group":{{"context_actor_hovercard":"GROUP","id":"{group_id}"}},'
        f'"owning_profile":{{"__typename":"User","name":"{name}","short_name":"X","id":"{uid}"}}}},'
        f'"post_id":"{post_id}","creation_time":{creation_time}{message_part}}}'
    )


@pytest.mark.asyncio
async def test_valid_response_extracts_one_record():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)
    body = make_post_json("111", EXPECTED_GROUP_ID, "Redacted Name", "999", 1786999800, "Test post text")
    resp = FakeResponse(body_bytes=body.encode("utf-8"))

    await adapter._handle_response(resp)

    records = adapter.snapshot()
    assert len(records) == 1
    rec = records[0]
    assert rec.post_id == "111"
    assert rec.group_id == EXPECTED_GROUP_ID
    assert rec.author_name == "Redacted Name"
    assert rec.text == "Test post text"
    assert rec.source == "network_response"

    assert adapter.counters["responses_seen"] == 1
    assert adapter.counters["json_responses"] == 1
    assert adapter.counters["accepted"] == 1
    assert adapter.counters["rejected"] == 0
    assert adapter.counters["duplicates"] == 0


@pytest.mark.asyncio
async def test_mixed_ads_and_reactions_only_accepts_valid_post():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)

    # A real post, plus ad/feedback-only noise objects that mention
    # post_id but lack the full invariant fields (no associated_group).
    valid_post = make_post_json("222", EXPECTED_GROUP_ID, "Redacted Name", "888", 1786999900, "Real post")
    ad_noise = '{"post_id":"333","ad_click_data":{"campaign":"x"},"sponsored":true}'
    reaction_noise = '{"post_id":"444","reaction_count":{"count":12},"reactors":[]}'
    body = f'[{valid_post},{ad_noise},{reaction_noise}]'
    resp = FakeResponse(body_bytes=body.encode("utf-8"))

    await adapter._handle_response(resp)

    records = adapter.snapshot()
    assert len(records) == 1
    assert records[0].post_id == "222"
    assert adapter.counters["accepted"] == 1
    # ad/reaction noise should not have produced accepted records
    assert all(r.post_id not in ("333", "444") for r in records)


@pytest.mark.asyncio
async def test_duplicate_post_across_responses_deduped():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)
    body = make_post_json("555", EXPECTED_GROUP_ID, "Redacted Name", "777", 1787000000, "Same post")
    resp1 = FakeResponse(body_bytes=body.encode("utf-8"))
    resp2 = FakeResponse(body_bytes=body.encode("utf-8"))  # simulates a second response repeating it

    await adapter._handle_response(resp1)
    await adapter._handle_response(resp2)

    records = adapter.snapshot()
    assert len(records) == 1
    assert adapter.counters["accepted"] == 1
    assert adapter.counters["duplicates"] == 1
    assert adapter.counters["candidate_records"] == 2  # seen twice, accepted once


@pytest.mark.asyncio
async def test_malformed_json_does_not_crash_and_accepts_nothing():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)
    # Truncated mid-object, as if the response was cut off
    body = '{"post_id":"666","creation_time":178699,"feedback":{"associated_group":{"id":"30505'
    resp = FakeResponse(body_bytes=body.encode("utf-8"))

    await adapter._handle_response(resp)  # should not raise

    records = adapter.snapshot()
    assert len(records) == 0
    assert adapter.counters["accepted"] == 0
    assert adapter.counters["rejected"] == 0  # parsed as text fine, just no valid record


@pytest.mark.asyncio
async def test_schema_drift_missing_fields_accepts_nothing():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)
    # post_id present but the field names Facebook uses have changed/renamed
    body = (
        '{"post_id":"777","story_creation_ts":1787000100,'
        '"group_context":{"gid":"305056891435827"},'
        '"author_info":{"display_name":"Redacted Name"}}'
    )
    resp = FakeResponse(body_bytes=body.encode("utf-8"))

    await adapter._handle_response(resp)

    records = adapter.snapshot()
    assert len(records) == 0
    assert adapter.counters["accepted"] == 0
    assert adapter.counters["candidate_records"] == 0  # never became a candidate; invariants unmet


@pytest.mark.asyncio
async def test_wrong_group_rejected():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)
    other_group_id = "999999999999999"
    body = make_post_json("888", other_group_id, "Redacted Name", "111", 1787000200, "Wrong group post")
    resp = FakeResponse(body_bytes=body.encode("utf-8"))

    await adapter._handle_response(resp)

    records = adapter.snapshot()
    assert len(records) == 0
    assert adapter.counters["accepted"] == 0
    assert all(r.group_id != other_group_id for r in records)


@pytest.mark.asyncio
async def test_response_body_read_failure_is_rejected_not_crashed():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)
    resp = FakeResponse(body_error=RuntimeError("simulated network read failure"))

    await adapter._handle_response(resp)  # should not raise

    records = adapter.snapshot()
    assert len(records) == 0
    assert adapter.counters["rejected"] == 1
    assert adapter.counters["accepted"] == 0


@pytest.mark.asyncio
async def test_scroll_phase_drop_tracking():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)

    # Fill and overflow the queue before marking scroll started
    adapter._queue = __import__("asyncio").Queue(maxsize=1)
    resp = FakeResponse(body_bytes=b'{}')

    adapter._on_response(resp)  # fills the queue (maxsize=1)
    adapter._on_response(resp)  # this one should be dropped as prelaunch

    assert adapter.counters["prelaunch_dropped"] == 1
    assert adapter.counters["scroll_phase_dropped"] == 0
    assert not adapter.has_scroll_phase_drops

    adapter.mark_scroll_started()
    adapter._on_response(resp)  # queue still full -> dropped, now scroll-phase

    assert adapter.counters["scroll_phase_dropped"] == 1
    assert adapter.has_scroll_phase_drops

    with pytest.raises(AssertionError):
        adapter.assert_no_scroll_phase_drops()
