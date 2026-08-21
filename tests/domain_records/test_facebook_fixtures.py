"""Fixture-driven serializer tests for the Facebook post normalization
boundary, per VIBE BOT review.

Uses checked-in JSON fixtures (tests/fixtures/facebook/posts_listen/) as
the source of truth, rather than inline dicts, so the contract is
reviewable independent of test code.
"""
import json
from pathlib import Path

import pytest

from facebook_camofox_client.domain_records.normalization import PostNormalizer, RejectedRecord

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "facebook" / "posts_listen"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_valid_post_normalizes_with_all_fields_preserved():
    fixture = load_fixture("recent_valid.json")
    normalizer = PostNormalizer()

    rec = normalizer.normalize(
        raw={
            "post_id": fixture["post_id"],
            "group_id": fixture["group_id"],
            "author_id": fixture["author_id"],
            "author_name": fixture["author_name"],
            "text": fixture["text"],
            "occurred_at": fixture["created_at"],
            "url": fixture["permalink"],
        },
        account_id="test-account",
        source_action="test-action",
        expected_group_id=fixture["group_id"],
    )

    assert rec.external_id == fixture["post_id"]
    assert rec.group_id == fixture["group_id"]
    assert rec.author["name"] == fixture["author_name"]
    assert rec.occurred_at is not None
    assert rec.occurred_at.isoformat().startswith("2026-08-20T12:03:00")


def test_missing_created_at_stays_null_not_fabricated():
    fixture = load_fixture("recent_missing_created_at.json")
    normalizer = PostNormalizer()

    rec = normalizer.normalize(
        raw={
            "post_id": fixture["post_id"],
            "group_id": fixture["group_id"],
            "text": fixture["text"],
            "occurred_at": fixture["created_at"],  # None
        },
        account_id="test-account",
        source_action="test-action",
        expected_group_id=fixture["group_id"],
    )

    # This is THE assertion that matters: occurred_at must be None, not
    # datetime.now()/utcnow(). A fabricated "now" would silently turn
    # "timestamp unavailable" into "posted just now" — a real data
    # integrity bug, not a convenience default.
    assert rec.occurred_at is None


def test_duplicate_post_id_across_two_responses_share_identity():
    """The normalizer itself doesn't dedupe (that's the adapter/action's
    job, already proven in test_native_response_adapter.py). This proves
    the fixture's two responses produce records with the SAME
    external_id, which is what the caller-level dedupe keys on."""
    fixture = load_fixture("recent_duplicate.json")
    normalizer = PostNormalizer()

    first = fixture["first_response"]
    second = fixture["second_response_same_post"]

    rec1 = normalizer.normalize(
        raw={"post_id": first["post_id"], "group_id": first["group_id"], "text": first["text"]},
        account_id="test-account", source_action="test-action",
        expected_group_id=first["group_id"],
    )
    rec2 = normalizer.normalize(
        raw={"post_id": second["post_id"], "group_id": second["group_id"], "text": second["text"]},
        account_id="test-account", source_action="test-action",
        expected_group_id=second["group_id"],
    )

    assert rec1.external_id == rec2.external_id == fixture["first_response"]["post_id"]
    # dedupe-by-post_id at the caller level (NativeResponseAdapter,
    # PostsListenAction's last_post_id check) is what collapses these
    # two normalized records into one emission — proven separately in
    # test_native_response_adapter.py's duplicate tests.


def test_wrong_group_record_is_rejected():
    fixture = load_fixture("recent_wrong_group.json")
    normalizer = PostNormalizer()
    post = fixture["post"]

    with pytest.raises(RejectedRecord) as exc_info:
        normalizer.normalize(
            raw={"post_id": post["post_id"], "group_id": post["group_id"], "text": post["text"]},
            account_id="test-account",
            source_action="test-action",
            expected_group_id=fixture["expected_group_id"],
        )

    assert exc_info.value.reason == "wrong_group"


def test_missing_post_id_is_rejected():
    fixture = load_fixture("recent_missing_post_id.json")
    normalizer = PostNormalizer()

    with pytest.raises(RejectedRecord) as exc_info:
        normalizer.normalize(
            raw={"post_id": fixture["post_id"], "group_id": fixture["group_id"], "text": fixture["text"]},
            account_id="test-account",
            source_action="test-action",
            expected_group_id=fixture["group_id"],
        )

    assert exc_info.value.reason == "missing_post_id"


def test_missing_group_id_is_rejected():
    normalizer = PostNormalizer()

    with pytest.raises(RejectedRecord) as exc_info:
        normalizer.normalize(
            raw={"post_id": "123", "group_id": "", "text": "no group id"},
            account_id="test-account",
            source_action="test-action",
        )

    assert exc_info.value.reason == "missing_group_id"


def test_expected_action_response_fixture_is_valid_json_and_matches_documented_shape():
    """This fixture documents the TARGET full action-response envelope
    (per VIBE BOT's richer contract: cursor block, coverage block,
    success/error shape). PostsListenOutput doesn't build this full
    shape yet — that's the next task, wiring PostsListenAction to emit
    this envelope. This test only proves the checked-in fixture itself
    is well-formed and matches the documented field set, so it's a
    reviewable source of truth for that future work."""
    fixture = load_fixture("expected_action_response.json")

    assert fixture["action"] == "posts.listen"
    assert fixture["success"] is True
    assert "group_id" in fixture["data"]
    assert "feed_mode" in fixture["data"]
    assert "posts" in fixture["data"]
    assert "cursor" in fixture["data"]
    assert set(fixture["data"]["cursor"].keys()) == {
        "previous_last_post_id", "last_post_id", "watermark", "advanced"
    }
    assert "coverage" in fixture["data"]
    assert set(fixture["data"]["coverage"].keys()) == {
        "responses_seen", "accepted", "duplicates", "rejected",
        "scroll_phase_dropped", "degraded"
    }
