"""Normalize raw Facebook extraction."""
from __future__ import annotations
import uuid
from datetime import datetime, UTC
from domain_records.models import NormalizedPostRecord

class PostNormalizer:
    def normalize(self, raw: dict, account_id: str, source_action: str) -> NormalizedPostRecord:
        return NormalizedPostRecord(
            record_id=f"rec-{uuid.uuid4().hex[:12]}",
            external_id=raw.get("post_id", "") or raw.get("external_id", ""),
            account_id=account_id,
            group_id=raw.get("group_id", ""),
            content=raw.get("content", "") or raw.get("message", ""),
            url=raw.get("url", "") or raw.get("permalink", ""),
            author={"id": raw.get("author_id", ""), "name": raw.get("author", "")},
            occurred_at=raw.get("occurred_at") or datetime.now(UTC),
            metrics={
                "likes": raw.get("likes", 0) or raw.get("metrics", {}).get("likes", 0),
                "comments": raw.get("comments", 0) or raw.get("metrics", {}).get("comments", 0),
                "shares": raw.get("shares", 0) or raw.get("metrics", {}).get("shares", 0),
            },
            matched_terms=raw.get("matched_terms", []),
            raw_extraction=raw,
        )