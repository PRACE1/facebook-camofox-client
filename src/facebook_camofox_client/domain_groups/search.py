"""Groups search action — wire the full vertical slice.

Sequence:
  groups.search envelope
    -> acquire session
    -> auth_guard.validate() [after cookies loaded, before surface opens]
    -> open_surface
    -> DOM extraction
    -> normalize post
    -> record_repo.save()   ← RECORDS COMMITTED
    -> cursor_repo.save()   ← CURSOR ADVANCES AFTER
    -> event emitter
    -> return GroupsSearchOutput
"""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_accounts.auth_guard import AuthGuard, AuthState
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.models import Cursor
from facebook_camofox_client.domain_cursors.repository import CursorRepository
from facebook_camofox_client.domain_events.models import DomainEvent
from facebook_camofox_client.domain_records.models import NormalizedPostRecord
from facebook_camofox_client.domain_records.normalization import PostNormalizer
from facebook_camofox_client.domain_records.repository import RecordRepository
from facebook_camofox_client.domain_groups.schemas import GroupsSearchInput, GroupsSearchOutput


class GroupsSearchAction:
    """Execute groups.search through Camofox.

    openmagpie.py must never pass a Camofox object, page, locator,
    cookie path, or proxy config here. The connector only sends
    normalized records and events outward.
    """

    def __init__(
        self,
        session_manager: CamofoxSessionManager,
        cursor_repo: CursorRepository,
        record_repo: RecordRepository,
        normalizer: PostNormalizer,
        event_emitter: Any,
        auth_guard: AuthGuard | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.cursor_repo = cursor_repo
        self.record_repo = record_repo
        self.normalizer = normalizer
        self.event_emitter = event_emitter
        self.auth_guard = auth_guard or AuthGuard()

    async def execute(self, envelope: ActionEnvelope) -> dict:
        input_data = GroupsSearchInput(**envelope.input)
        scope_key = (
            f"{envelope.account_id}"
            f"-{'-'.join(input_data.group_ids)}"
            f"-{'-'.join(input_data.terms)}"
        )

        await self._emit("groups.search_started", envelope, {})

        cursor = await self.cursor_repo.load(
            cursor_key="groups-search",
            account_id=envelope.account_id,
            scope_key=scope_key,
        )

        session = await self.session_manager.acquire(envelope.account_id)
        try:
            # Auth guard fires AFTER cookies are loaded into context
            # and BEFORE the requested surface opens.
            page_title, page_url = await session.get_current_page_state()
            auth_result = await self.auth_guard.validate(
                page_title=page_title, page_url=page_url
            )

            if auth_result.state != AuthState.authenticated:
                await self._emit(
                    "groups.search_failed",
                    envelope,
                    {"reason": auth_result.state, "requires_action": auth_result.requires_action},
                )
                return GroupsSearchOutput(results=[], cursor={}, matched_terms=[]).model_dump()

            for gid in input_data.group_ids:
                await session.open_surface("facebook_group", {"group_id": gid})

            raw = await session.execute(
                "facebook_group_search",
                {
                    "terms": input_data.terms,
                    "limit": input_data.limit,
                    "cursor": cursor.opaque_cursor if cursor else None,
                    "since": input_data.since,
                },
            )

            records: list[NormalizedPostRecord] = []
            for post in raw.get("results", []):
                rec = self.normalizer.normalize(
                    raw=post,
                    account_id=envelope.account_id,
                    source_action=envelope.action_id,
                )
                dedupe_key = f"{rec.account_id}:{rec.group_id}:{rec.external_id}"
                if await self.record_repo.exists(dedupe_key):
                    continue

                # RECORDS COMMITTED before cursor advances
                await self.record_repo.save(rec)
                records.append(rec)
                await self._emit(
                    "groups.result_found",
                    envelope,
                    {"record_id": rec.record_id, "external_id": rec.external_id},
                )

            # CURSOR ADVANCES only after all records are persisted
            new_cursor = self._build_cursor(cursor, records, scope_key, envelope.account_id)
            await self.cursor_repo.save(new_cursor)

            await self._emit(
                "groups.search_completed",
                envelope,
                {"records_found": len(records)},
            )
            return GroupsSearchOutput(
                results=[r.model_dump() for r in records],
                cursor=new_cursor.model_dump(),
                matched_terms=input_data.terms,
            ).model_dump()

        except Exception as exc:
            await self._emit("groups.search_failed", envelope, {"reason": str(exc)})
            raise
        finally:
            await self.session_manager.release(session.session_id)

    def _build_cursor(
        self,
        old: Cursor | None,
        records: list[NormalizedPostRecord],
        scope_key: str,
        account_id: str,
    ) -> Cursor:
        last = records[-1] if records else None
        return Cursor(
            cursor_key="groups-search",
            action_type="groups.search",
            account_id=last.account_id if last else (old.account_id if old else account_id),
            scope_key=scope_key,
            last_post_id=last.external_id if last else (old.last_post_id if old else ""),
            watermark=last.occurred_at if last else datetime.now(UTC),
            opaque_cursor=f"cursor-{datetime.now(UTC).timestamp()}",
        )

    async def _emit(self, event_type: str, envelope: ActionEnvelope, payload: dict) -> None:
        dedupe = f"{envelope.action_id}-{event_type}-{datetime.now(UTC).timestamp()}"
        await self.event_emitter.emit(
            event_type=event_type,
            payload={"action_id": envelope.action_id, **payload},
            dedupe_key=dedupe,
        )