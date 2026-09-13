"""Additional fixture per VIBE BOT review: one response body containing
two valid posts, a duplicate of one of them, and a wrong-group record —
all in a single call, not three separate scenarios."""
import pytest

from facebook_camofox_client.domain_extraction.response_capture import NativeResponseAdapter

EXPECTED_GROUP_ID = "305056891435827"


class FakeResponse:
    def __init__(self, status: int = 200, content_type: str = "application/json",
                 body_bytes: bytes | None = None):
        self.status = status
        self.headers = {"content-type": content_type}
        self._body_bytes = body_bytes or b""

    async def body(self) -> bytes:
        return self._body_bytes


def make_post_json(post_id: str, group_id: str, name: str, uid: str,
                    creation_time: int, message: str | None = None) -> str:
    message_part = f',"message":{{"text":"{message}"}}' if message is not None else ""
    return (
        f'{{"feedback":{{"associated_group":{{"context_actor_hovercard":"GROUP","id":"{group_id}"}},'
        f'"owning_profile":{{"__typename":"User","name":"{name}","short_name":"X","id":"{uid}"}}}},'
        f'"post_id":"{post_id}","creation_time":{creation_time}{message_part}}}'
    )


@pytest.mark.asyncio
async def test_two_posts_one_duplicate_one_wrong_group_in_single_response():
    adapter = NativeResponseAdapter(expected_group_id=EXPECTED_GROUP_ID)

    post_a = make_post_json("100", EXPECTED_GROUP_ID, "Alice", "1", 1786999800, "Post A text")
    post_b = make_post_json("200", EXPECTED_GROUP_ID, "Bob", "2", 1786999900, "Post B text")
    duplicate_of_a = make_post_json("100", EXPECTED_GROUP_ID, "Alice", "1", 1786999800, "Post A text")
    wrong_group = make_post_json("300", "999999999999999", "Carol", "3", 1787000000, "Wrong group post")

    body = f'[{post_a},{post_b},{duplicate_of_a},{wrong_group}]'
    resp = FakeResponse(body_bytes=body.encode("utf-8"))

    await adapter._handle_response(resp)

    records = adapter.snapshot()
    record_ids = {r.post_id for r in records}

    assert record_ids == {"100", "200"}
    assert "300" not in record_ids  # wrong group excluded

    assert adapter.counters["accepted"] == 2
    assert adapter.counters["duplicates"] == 1
    # the within-response duplicate is caught inside extract_from_relay
    # itself and never reaches the per-record loop, so candidate_records
    # only counts the two genuinely-distinct accepted posts
    assert adapter.counters["candidate_records"] == 2
