"""Groups search — first read-only vertical slice."""
from __future__ import annotations
import dataclasses

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.schemas import GroupsSearchInput, GroupsSearchOutput
from facebook_camofox_client.domain_records.normalization import PostNormalizer


class GroupsSearchAction:
    def __init__(self, session_manager, cursor_repo, normalizer, event_emitter):
        self.session_manager = session_manager
        self.cursor_repo = cursor_repo
        self.normalizer = normalizer
        self.event_emitter = event_emitter

    async def execute(self, envelope: ActionEnvelope) -> GroupsSearchOutput:
        input_data = GroupsSearchInput(**envelope.input)
        session = await self.session_manager.acquire(envelope.account_id)
        try:
            # 1. verify auth
            page = await session.open_surface(
                "facebook_group",
                {"group_id": input_data.group_ids[0]}
            )
            title = await page.title()
            url = page.url

            if "login" in url or "log in" in title.lower():
                await self.event_emitter.emit(
                    "groups.search_failed",
                    {"action_id": envelope.action_id, "reason": "auth_required"},
                    dedupe_key=f"{envelope.action_id}-failed"
                )
                return GroupsSearchOutput(results=[], cursor={}, matched_terms=[])

            # 2. extract
            raw_results = await session.execute("facebook_group_search", {
                "group_id": input_data.group_ids[0],
                "terms": input_data.terms,
                "limit": input_data.limit,
            })

            # 3. normalize — degraded DOM fallbacks and empty-text records are excluded
            clean_records = []
            degraded_count = 0
            for post in raw_results.get("results", []):
                raw_dict = dataclasses.asdict(post) if hasattr(post, "__dataclass_fields__") else post

                if raw_dict.get("source") == "dom" or not raw_dict.get("text"):
                    degraded_count += 1
                    continue

                rec = self.normalizer.normalize(
                    raw=raw_dict,
                    account_id=envelope.account_id,
                    source_action=envelope.action_id
                )
                clean_records.append(rec)
                await self.event_emitter.emit(
                    "groups.result_found",
                    {"action_id": envelope.action_id, "record_id": rec.record_id},
                    dedupe_key=f"{envelope.action_id}-{rec.record_id}"
                )

            await self.event_emitter.emit(
                "groups.search_completed",
                {
                    "action_id": envelope.action_id,
                    "records_found": len(clean_records),
                    "degraded_count": degraded_count,
                },
                dedupe_key=f"{envelope.action_id}-completed"
            )

            return GroupsSearchOutput(
                results=[r.model_dump() for r in clean_records],
                cursor={},
                matched_terms=input_data.terms
            )

        except Exception as exc:
            await self.event_emitter.emit(
                "groups.search_failed",
                {"action_id": envelope.action_id, "reason": str(exc)},
                dedupe_key=f"{envelope.action_id}-failed"
            )
            raise

        finally:
            await self.session_manager.release(session)