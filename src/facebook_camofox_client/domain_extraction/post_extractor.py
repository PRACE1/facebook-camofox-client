"""PostExtractor: extracts posts from a Facebook group page.

Architecture (per VIBE BOT review):
- Relay (embedded server-side JSON) is the PRIMARY extraction path.
- DOM ([role="article"]) is a FALLBACK, only used to cover a shortfall.
- Every record is tagged with source="relay" or source="dom".
- Failures are distinguished, not collapsed into one generic message.
- This parses data already embedded in the page. It does NOT replay or
  call Facebook's private GraphQL endpoints directly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any


class FailureReason(str, Enum):
    NO_PAYLOAD_FOUND = "no_embedded_payload_found"
    SCHEMA_CHANGED = "payload_found_but_schema_changed"
    GROUP_MISMATCH = "records_found_but_group_validation_failed"
    INSUFFICIENT_RECORDS = "fewer_than_requested_posts_available"


@dataclass
class ExtractedPost:
    post_id: str
    group_id: str
    author_name: str | None
    author_id: str | None
    text: str | None
    created_at: str | None  # ISO 8601, or None if unparseable
    permalink: str
    collected_at: str
    source: str  # "relay" | "dom"


@dataclass
class ExtractionResult:
    records: list[ExtractedPost] = field(default_factory=list)
    failure_reason: FailureReason | None = None
    warning: str | None = None
    duplicate_candidates: int = 0

    @property
    def ok(self) -> bool:
        return self.failure_reason is None


# ---------------------------------------------------------------------------
# Relay (embedded JSON) extraction — primary path
# ---------------------------------------------------------------------------

_POST_ID_RE = re.compile(r'"post_id":"(\d+)"')
_CREATION_TIME_RE = re.compile(r'"creation_time":(\d+)')
_OWNING_PROFILE_RE = re.compile(
    r'"owning_profile":\{"__typename":"User","name":"([^"]*)"[^}]*?"id":"(\d+)"'
)
_ASSOCIATED_GROUP_RE = re.compile(
    r'"associated_group":\{"context_actor_hovercard":"GROUP","id":"(\d+)"'
)
_MESSAGE_TEXT_RE = re.compile(r'"message":\{"text":"((?:[^"\\]|\\.)*)"')

_WINDOW_BEFORE = 1500
_WINDOW_AFTER_MIN = 4000
_WINDOW_AFTER_MAX = 15000


def _decode_json_string_fragment(raw: str) -> str:
    """Decode a JSON-escaped string fragment (handles \\n, \\", \\/ etc.)."""
    try:
        return json.loads(f'"{raw}"')
    except (json.JSONDecodeError, ValueError):
        return raw


def _extract_candidates(html: str) -> list[re.Match]:
    return list(_POST_ID_RE.finditer(html))


def extract_from_relay(
    html: str,
    expected_group_id: str,
    min_records: int = 3,
    debug: bool = False,
) -> ExtractionResult:
    """Extract posts from embedded Relay/GraphQL JSON in the page HTML."""
    candidates = _extract_candidates(html)

    if not candidates:
        return ExtractionResult(failure_reason=FailureReason.NO_PAYLOAD_FOUND)

    records: dict[str, ExtractedPost] = {}
    group_mismatches = 0
    schema_incomplete = 0
    duplicate_candidates = 0
    now_iso = datetime.now(UTC).isoformat()

    for idx, match in enumerate(candidates):
        post_id = match.group(1)
        if post_id in records:
            duplicate_candidates += 1
            continue

        # Bound both directions by neighboring post_id matches (capped),
        # so we never borrow a neighboring post's fields.
        prev_end = candidates[idx - 1].end() if idx > 0 else 0
        next_start = (
            candidates[idx + 1].start()
            if idx + 1 < len(candidates)
            else len(html)
        )

        backward_limit = max(0, min(_WINDOW_BEFORE, match.start() - prev_end))
        forward_limit = max(_WINDOW_AFTER_MIN, min(_WINDOW_AFTER_MAX, next_start - match.end()))

        start = max(0, prev_end, match.start() - backward_limit)
        end = min(len(html), match.end() + forward_limit, next_start)
        window = html[start:end]

        group_match = _ASSOCIATED_GROUP_RE.search(window)
        creation_match = _CREATION_TIME_RE.search(window)
        author_match = _OWNING_PROFILE_RE.search(window)
        text_match = _MESSAGE_TEXT_RE.search(window)

        if group_match is None or creation_match is None:
            # Core fields missing -> schema likely shifted for this record
            schema_incomplete += 1
            if debug:
                missing = []
                if group_match is None:
                    missing.append("associated_group")
                if creation_match is None:
                    missing.append("creation_time")
                print(f"  [SKIP schema] post_id={post_id} missing={missing}")
            continue

        group_id = group_match.group(1)
        if group_id != str(expected_group_id):
            group_mismatches += 1
            if debug:
                print(f"  [SKIP group] post_id={post_id} found_group={group_id}")
            continue

        creation_time = int(creation_match.group(1))
        try:
            created_at = datetime.fromtimestamp(creation_time, tz=UTC).isoformat()
        except (ValueError, OSError):
            created_at = None

        author_name = author_match.group(1) if author_match else None
        author_id = author_match.group(2) if author_match else None
        text = _decode_json_string_fragment(text_match.group(1)) if text_match else None

        permalink = f"https://web.facebook.com/groups/{group_id}/posts/{post_id}/"

        records[post_id] = ExtractedPost(
            post_id=post_id,
            group_id=group_id,
            author_name=author_name,
            author_id=author_id,
            text=text,
            created_at=created_at,
            permalink=permalink,
            collected_at=now_iso,
            source="relay",
        )

    result_records = list(records.values())

    if not result_records:
        if group_mismatches and not schema_incomplete:
            return ExtractionResult(failure_reason=FailureReason.GROUP_MISMATCH, duplicate_candidates=duplicate_candidates)
        return ExtractionResult(failure_reason=FailureReason.SCHEMA_CHANGED, duplicate_candidates=duplicate_candidates)

    if len(result_records) < min_records:
        return ExtractionResult(
            records=result_records,
            failure_reason=FailureReason.INSUFFICIENT_RECORDS,
            warning=(
                f"Only {len(result_records)}/{min_records} valid records found "
                f"({schema_incomplete} skipped for incomplete schema, "
                f"{group_mismatches} skipped for group mismatch)."
            ),
            duplicate_candidates=duplicate_candidates,
        )

    warning = None
    if schema_incomplete or group_mismatches:
        warning = (
            f"{schema_incomplete} candidate(s) skipped (incomplete schema), "
            f"{group_mismatches} skipped (group mismatch)."
        )

    return ExtractionResult(records=result_records, warning=warning, duplicate_candidates=duplicate_candidates)


# ---------------------------------------------------------------------------
# DOM extraction — fallback path (requires a live Playwright page)
# ---------------------------------------------------------------------------

async def extract_from_dom(page: Any, expected_group_id: str) -> ExtractionResult:
    """Fallback extraction using [role="article"] elements.

    Used only to cover a shortfall when Relay extraction under-delivers.
    This is intentionally minimal — a real DOM adapter needs its own
    fixture-driven test suite per VIBE BOT's recommendation, since FB's
    class names rotate. This anchors on role/aria only.
    """
    now_iso = datetime.now(UTC).isoformat()
    articles = page.locator('[role="article"]')
    count = await articles.count()

    records: list[ExtractedPost] = []
    for i in range(count):
        article = articles.nth(i)

        # Skip elements that are actually comments, not top-level posts
        aria_label = await article.get_attribute("aria-label") or ""
        if "comment" in aria_label.lower():
            continue

        text_content = await article.inner_text()
        if not text_content.strip():
            continue

        # DOM path can't reliably recover post_id/permalink without
        # clicking through — flagged as a known limitation.
        records.append(
            ExtractedPost(
                post_id=f"dom-unresolved-{i}",
                group_id=str(expected_group_id),
                author_name=None,
                author_id=None,
                text=text_content.strip()[:2000],
                created_at=None,
                permalink="",
                collected_at=now_iso,
                source="dom",
            )
        )

    if not records:
        return ExtractionResult(failure_reason=FailureReason.NO_PAYLOAD_FOUND)
    return ExtractionResult(records=records, warning="DOM fallback: post_id/permalink unresolved")


# ---------------------------------------------------------------------------
# Combined pipeline
# ---------------------------------------------------------------------------

async def extract(
    page: Any,
    expected_group_id: str,
    min_records: int = 3,
) -> ExtractionResult:
    """Relay primary, DOM fallback only to cover a shortfall. Dedupe by post_id."""
    html = await page.content()
    relay_result = extract_from_relay(html, expected_group_id, min_records=min_records)

    if len(relay_result.records) >= min_records:
        return relay_result

    dom_result = await extract_from_dom(page, expected_group_id)

    seen_ids = {r.post_id for r in relay_result.records}
    combined = list(relay_result.records)
    for rec in dom_result.records:
        if rec.post_id not in seen_ids:
            combined.append(rec)
            seen_ids.add(rec.post_id)

    warning_parts = []
    if relay_result.warning:
        warning_parts.append(f"relay: {relay_result.warning}")
    if dom_result.records:
        warning_parts.append("dom fallback was used to cover shortfall")

    if len(combined) < min_records:
        return ExtractionResult(
            records=combined,
            failure_reason=FailureReason.INSUFFICIENT_RECORDS,
            warning="; ".join(warning_parts) or None,
        )

    return ExtractionResult(records=combined, warning="; ".join(warning_parts) or None)
