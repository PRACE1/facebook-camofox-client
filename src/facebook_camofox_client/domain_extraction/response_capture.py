"""NativeResponseAdapter: observes response bodies the page natively
requests during scroll (per VIBE BOT sign-off). Does NOT construct
requests, replay GraphQL, or call any endpoint directly — purely a
passive listener on traffic the page generates on its own.

Guardrails (per review):
- Attach before navigation/scroll; only inspect responses from this
  page/frame.
- Don't log headers, cookies, auth material, or raw response bodies
  outside short-lived fixture capture.
- Wait for the response body to actually be ready before reading it.
- Push work onto a bounded queue; don't do heavy parsing in the event
  callback itself.
- Don't depend on a fragile GraphQL URL/operation name as the primary
  filter — gate on status/content-type, then parse defensively.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .post_extractor import ExtractedPost, extract_from_relay

_QUEUE_MAXSIZE = 50
_ANTI_HIJACK_PREFIX = "for (;;);"


class NativeResponseAdapter:
    def __init__(self, expected_group_id: str) -> None:
        self.expected_group_id = str(expected_group_id)
        self._records: dict[str, ExtractedPost] = {}
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._worker_task: asyncio.Task | None = None
        self._stopped = False
        self._scroll_started = False

        self.counters = {
            "responses_seen": 0,
            "json_responses": 0,
            "candidate_records": 0,
            "accepted": 0,
            "duplicates": 0,
            "rejected": 0,
            "prelaunch_dropped": 0,
            "scroll_phase_dropped": 0,
        }

    def mark_scroll_started(self) -> None:
        """Call once scrolling begins. Drops after this point are a real
        coverage risk, not initial-burst noise, and get tracked separately."""
        self._scroll_started = True

    @property
    def has_scroll_phase_drops(self) -> bool:
        return self.counters["scroll_phase_dropped"] > 0

    def assert_no_scroll_phase_drops(self) -> None:
        if self.has_scroll_phase_drops:
            raise AssertionError(
                f"{self.counters['scroll_phase_dropped']} response(s) dropped during "
                f"the scroll phase — this is a real coverage risk, not initial-burst noise."
            )

    def attach(self, page: Any) -> None:
        """Attach the listener. Call this BEFORE page.goto()."""
        page.on("response", self._on_response)

    def start(self) -> None:
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        self._stopped = True
        if self._worker_task is not None:
            await self._queue.put(None)  # sentinel to unblock worker
            await self._worker_task

    def _on_response(self, response: Any) -> None:
        # Keep the event callback itself cheap: just enqueue.
        if self._stopped:
            return
        try:
            self._queue.put_nowait(response)
        except asyncio.QueueFull:
            if self._scroll_started:
                self.counters["scroll_phase_dropped"] += 1
            else:
                self.counters["prelaunch_dropped"] += 1

    async def _worker(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            await self._handle_response(item)

    async def _handle_response(self, response: Any) -> None:
        self.counters["responses_seen"] += 1

        try:
            if response.status != 200:
                return

            content_type = (response.headers or {}).get("content-type", "")
            if not any(t in content_type for t in ("json", "javascript", "text")):
                return

            body_bytes = await response.body()
        except Exception:
            self.counters["rejected"] += 1
            return

        try:
            text = body_bytes.decode("utf-8", errors="ignore")
        except Exception:
            self.counters["rejected"] += 1
            return

        if text.startswith(_ANTI_HIJACK_PREFIX):
            text = text[len(_ANTI_HIJACK_PREFIX):]

        if '"post_id"' not in text:
            return  # cheap pre-filter before running full extraction

        self.counters["json_responses"] += 1
        self._scan_text(text)

    def _scan_text(self, text: str) -> None:
        # Reuse the same validated windowed-extraction logic as the
        # page-load adapter (same invariants: post_id, associated_group,
        # creation_time).
        result = extract_from_relay(text, self.expected_group_id, min_records=0)
        for rec in result.records:
            self.counters["candidate_records"] += 1
            if rec.post_id in self._records:
                self.counters["duplicates"] += 1
                continue
            rec.source = "network_response"
            self._records[rec.post_id] = rec
            self.counters["accepted"] += 1

    def merge_external(self, records: list[ExtractedPost]) -> None:
        """Merge records found by another adapter (e.g. page-load Relay)."""
        for rec in records:
            if rec.post_id not in self._records:
                self._records[rec.post_id] = rec

    def snapshot(self) -> list[ExtractedPost]:
        return list(self._records.values())
