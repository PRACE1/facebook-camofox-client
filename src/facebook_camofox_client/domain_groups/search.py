"""Groups search action implementation."""
from __future__ import annotations
from datetime import datetime, UTC
from typing import Any
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.models import Cursor
from facebook_camofox_client.domain_events.models import DomainEvent
from facebook_camofox_client.domain_records.models import NormalizedPostRecord
from facebook_camofox_client.domain_records.normalization import PostNormalizer
from facebook_camofox_client.domain_groups.schemas import GroupsSearchInput, GroupsSearchOutput

class GroupsSearchAction:
    """Execute groups.search through Camofox."""

    def __init__(self, session_manager: CamofoxSessionManager, cursor_repo: Any, normalizer: PostNormalizer, event_emitter: Any) -> None:
        self.session_manager = session_manager
        self.cursor_repo = cursor_repo
        self.normalizer = normalizer
        self.event_emitter = event_emitter

    async def execute(self, envelope: ActionEnvelope) -> GroupsSearchOutput:
        input_data = GroupsSearchInput(**envelope.input)
        scope_key = f"{envelope.account_id}-{'-' .join(input_data.group_ids)}-{'-' .join(input_data.terms)}"
        await self._emit("groups.search_started", envelope, {})
        cursor = await self.cursor_repo.load(cursor_key="groups-search", account_id=envelope.account_id, scope_key=scope_key)
        session = await self.session_manager.acquire(envelope.account_id)
        try:
            auth = await session.auth_guard()
            if not auth.get("authenticated"):
                await self._emit("groups.search_failed", envelope, {"reason": "auth_required"})
                return GroupsSearchOutput(results=[], cursor={}, matched_terms=[])
            for gid in input_data.group_ids:
                await session.open_surface("facebook_group", {"group_id": gid})
            raw = await session.execute("facebook_group_search", {"terms": input_data.terms, "limit": input_data.limit, "cursor": cursor.opaque_cursor if cursor else None, "since": input_data.since})
            records: list[NormalizedPostRecord] = []
            for post in raw.get("results", []):
                rec = self.normalizer.normalize(raw=post, account_id=envelope.account_id, source_action=envelope.action_id)
                records.append(rec)
                await self._emit("groups.result_found", envelope, {"record_id": rec.record_id, "external_id": rec.external_id})
            new_cursor = self._build_cursor(cursor, records, scope_key)
            await self.cursor_repo.save(new_cursor)
            await self._emit("groups.search_completed", envelope, {"records_found": len(records)})
            return GroupsSearchOutput(results=[r.model_dump() for r in records], cursor=new_cursor.model_dump(), matched_terms=input_data.terms)
        except Exception as exc:
            await self._emit("groups.search_failed", envelope, {"reason": str(exc)})
            raise
        finally:
            await self.session_manager.release(session.session_id)

    def _build_cursor(self, old: Cursor | None, records: list[NormalizedPostRecord], scope_key: str) -> Cursor:
        last = records[-1] if records else None
        return Cursor(
            cursor_key="groups-search",
            action_type="groups.search",
            account_id=last.account_id if last else (old.account_id if old else ""),
            scope_key=scope_key,
            last_post_id=last.external_id if last else (old.last_post_id if old else ""),
            watermark=last.occurred_at if last else datetime.now(UTC),
            opaque_cursor=f"cursor-{datetime.now(UTC).timestamp()}",
        )

    async def _emit(self, event_type: str, envelope: ActionEnvelope, payload: dict) -> None:
        dedupe = f"{envelope.action_id}-{event_type}-{datetime.now(UTC).timestamp()}"
        await self.event_emitter.emit(event_type=event_type, payload={"action_id": envelope.action_id, **payload}, dedupe_key=dedupe)