"""Normalize raw Facebook extraction."""
from __future__ import annotations

import uuid
from datetime import datetime, UTC

from facebook_camofox_client.domain_records.models import NormalizedPostRecord


class RejectedRecord(Exception):
    """Raised when a raw record fails identity/integrity validation and
    must not be normalized or emitted — not a processing error, a
    deliberate rejection."""

    def __init__(self, reason: str, raw: dict):
        self.reason = reason
        self.raw = raw
        super().__init__(reason)


def validate_identity(raw: dict, expected_group_id: str | None = None) -> None:
    """Raise RejectedRecord if the raw post lacks a usable identity.

    A record must never be silently accepted with a fabricated or empty
    post_id/group_id — that data would look real downstream while being
    fiction.
    """
    post_id = raw.get("post_id") or raw.get("external_id")
    if not post_id:
        raise RejectedRecord("missing_post_id", raw)

    group_id = raw.get("group_id")
    if not group_id:
        raise RejectedRecord("missing_group_id", raw)

    if expected_group_id is not None and str(group_id) != str(expected_group_id):
        raise RejectedRecord("wrong_group", raw)


class PostNormalizer:
    def normalize(self, raw: dict, account_id: str, source_action: str,
                   expected_group_id: str | None = None) -> NormalizedPostRecord:
        # Validate identity before doing anything else — a record that
        # fails this must never reach the caller as a "normalized" post.
        validate_identity(raw, expected_group_id=expected_group_id)

        # occurred_at: preserve None when the source genuinely didn't
        # provide a trustworthy timestamp. Do NOT fabricate "now" —
        # that silently turns "unknown time" into "posted just now",
        # which is a real data-integrity bug, not a convenience default.
        occurred_at = raw.get("occurred_at")
        if occurred_at is not None and not isinstance(occurred_at, datetime):
            try:
                occurred_at = datetime.fromisoformat(str(occurred_at).replace("Z", "+00:00"))
            except ValueError:
                occurred_at = None

        return NormalizedPostRecord(
            record_id=f"rec-{uuid.uuid4().hex[:12]}",
            external_id=raw.get("post_id") or raw.get("external_id"),
            account_id=account_id,
            group_id=raw.get("group_id"),
            content=raw.get("content", "") or raw.get("text", "") or raw.get("message", ""),
            url=raw.get("url", "") or raw.get("permalink", ""),
            author={"id": raw.get("author_id", ""), "name": raw.get("author", "") or raw.get("author_name", "")},
            occurred_at=occurred_at,
            metrics={
                "likes": raw.get("likes", 0) or raw.get("metrics", {}).get("likes", 0),
                "comments": raw.get("comments", 0) or raw.get("metrics", {}).get("comments", 0),
                "shares": raw.get("shares", 0) or raw.get("metrics", {}).get("shares", 0),
            },
            matched_terms=raw.get("matched_terms", []),
            raw_extraction=raw,
        )
