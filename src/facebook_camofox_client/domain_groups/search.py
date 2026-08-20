"""Groups search — first read-only vertical slice."""
from __future__ import annotations

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.schemas import GroupsSearchInput, GroupsSearchOutput
from facebook_camofox_client.domain_records.normalization import PostNormalizer


def _is_degraded(post: dict) -> bool:
    """A record is degraded if it's a DOM fallback (post_id can't be
    resolved) or has no usable text — these are excluded from clean
    results, not silently normalized as if they were real coverage."""
    post_id = post.get("post_id", "")
    if isinstance(post_id, str) and post_id.startswith("dom-unresolved"):
        return True
    text = post.get("text")
    if not text:
        return True
    return False


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

            # 2. extract via NativeResponseAdapter + page-load Relay
            raw_results = await session.execute("facebook_group_search", {
                "group_id": input_data.group_ids[0],
                "terms": input_data.terms,
                "limit": input_data.limit,
            })

            counters = raw_results.get("counters", {}) or {}
            scroll_phase_dropped = counters.get("scroll_phase_dropped", 0)

            # 3. classify degraded records, normalize only clean ones
            records = []
            degraded_count = 0
            for post in raw_results.get("results", []):
                # ExtractedPost dataclass or dict, normalize to dict either way
                post_dict = post if isinstance(post, dict) else post.__dict__

                if _is_degraded(post_dict):
                    degraded_count += 1
                    continue

                rec = self.normalizer.normalize(
                    raw={
                        **post_dict,
                        "group_id": post_dict.get("group_id") or "",
                        "content": post_dict.get("content") or post_dict.get("text") or "",
                        "url": post_dict.get("url") or post_dict.get("permalink") or "",
                        "author": post_dict.get("author") or post_dict.get("author_name") or "",
                        "occurred_at": post_dict.get("occurred_at") or post_dict.get("created_at"),
                    },
                    account_id=envelope.account_id,
                    source_action=envelope.action_id
                )
                records.append(rec)
                await self.event_emitter.emit(
                    "groups.result_found",
                    {"action_id": envelope.action_id, "record_id": rec.record_id},
                    dedupe_key=f"{envelope.action_id}-{rec.record_id}"
                )

            # 4. coverage is degraded (not clean) if any responses were
            # dropped during the active scroll phase — this is a real
            # gap, not noise, per review. Never silently report clean.
            is_degraded = scroll_phase_dropped > 0 or degraded_count > 0

            await self.event_emitter.emit(
                "groups.search_completed",
                {
                    "action_id": envelope.action_id,
                    "records_found": len(records),
                    "degraded_count": degraded_count,
                    "scroll_phase_dropped": scroll_phase_dropped,
                    "degraded": is_degraded,
                },
                dedupe_key=f"{envelope.action_id}-completed"
            )

            return GroupsSearchOutput(
                results=[r.model_dump() for r in records],
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
