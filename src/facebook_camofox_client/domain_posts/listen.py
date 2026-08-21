"""Posts listen: continuous polling for new posts in a group.

Separate action from groups.search per review -- same session lifecycle
shape (acquire -> auth check -> extract -> release), but persists a
cursor across calls so repeat polls only emit genuinely new posts, even
across a dropped/reconnected session.

Reconnect safety: a fresh session re-extracts the same recent posts on
every poll. The persisted cursor (last_post_id + watermark) is what
filters out posts already emitted, not any in-memory session state.

Identity safety: a record missing post_id/group_id, or belonging to the
wrong group, is rejected individually (RejectedRecord) rather than
crashing the whole poll or being silently normalized with fabricated
empty-string/current-time fallbacks.
"""
from __future__ import annotations

from datetime import datetime

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_posts.schemas import PostsListenInput, PostsListenOutput
from facebook_camofox_client.domain_records.normalization import RejectedRecord


def _parse_created_at(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_degraded(post: dict) -> bool:
    post_id = post.get("post_id", "")
    if isinstance(post_id, str) and post_id.startswith("dom-unresolved"):
        return True
    if not post.get("text"):
        return True
    return False


class PostsListenAction:
    CURSOR_KEY = "posts-listen"

    def __init__(self, session_manager, cursor_repo, normalizer, event_emitter):
        self.session_manager = session_manager
        self.cursor_repo = cursor_repo
        self.normalizer = normalizer
        self.event_emitter = event_emitter

    async def execute(self, envelope: ActionEnvelope) -> PostsListenOutput:
        input_data = PostsListenInput(**envelope.input)
        group_id = input_data.group_id
        scope_key = group_id

        cursor = await self.cursor_repo.load(
            cursor_key=self.CURSOR_KEY,
            account_id=envelope.account_id,
            scope_key=scope_key,
        )
        watermark = cursor.watermark if cursor else None
        last_post_id = cursor.last_post_id if cursor else None

        session = await self.session_manager.acquire(envelope.account_id)
        try:
            page = await session.open_surface("facebook_group", {"group_id": group_id})
            title = await page.title()
            url = page.url

            if "login" in url or "log in" in title.lower():
                await self.event_emitter.emit(
                    "posts.listen_failed",
                    {"action_id": envelope.action_id, "reason": "auth_required"},
                    dedupe_key=f"{envelope.action_id}-failed",
                )
                return PostsListenOutput(new_posts=[], cursor_advanced=False)

            raw_results = await session.execute("facebook_group_search", {
                "group_id": group_id,
                "terms": input_data.terms,
                "limit": input_data.limit,
            })

            counters = raw_results.get("counters", {}) or {}
            scroll_phase_dropped = counters.get("scroll_phase_dropped", 0)

            new_records = []
            degraded_count = 0
            rejected_count = 0
            newest_watermark = watermark
            newest_post_id = last_post_id

            for post in raw_results.get("results", []):
                post_dict = post if isinstance(post, dict) else post.__dict__

                if _is_degraded(post_dict):
                    degraded_count += 1
                    continue

                post_id = post_dict.get("post_id")
                created_at = _parse_created_at(
                    post_dict.get("created_at") or post_dict.get("occurred_at")
                )

                if post_id is not None and post_id == last_post_id:
                    continue
                if watermark is not None and created_at is not None and created_at <= watermark:
                    continue

                try:
                    rec = self.normalizer.normalize(
                        raw={
                            **post_dict,
                            "group_id": post_dict.get("group_id") or group_id,
                            "content": post_dict.get("content") or post_dict.get("text") or "",
                            "url": post_dict.get("url") or post_dict.get("permalink") or "",
                            "author": post_dict.get("author") or post_dict.get("author_name") or "",
                            "occurred_at": created_at,
                        },
                        account_id=envelope.account_id,
                        source_action=envelope.action_id,
                        expected_group_id=group_id,
                    )
                except RejectedRecord:
                    # A bad individual record must not crash the whole
                    # poll or silently become a fabricated post — skip
                    # it, count it, keep processing the rest.
                    rejected_count += 1
                    continue

                new_records.append(rec)
                if created_at is not None and (newest_watermark is None or created_at > newest_watermark):
                    newest_watermark = created_at
                    newest_post_id = post_id

                await self.event_emitter.emit(
                    "posts.new",
                    {"action_id": envelope.action_id, "record_id": rec.record_id, "post_id": post_id},
                    dedupe_key=f"{envelope.action_id}-{rec.record_id}",
                )

            cursor_advanced = newest_watermark != watermark or newest_post_id != last_post_id
            if cursor_advanced:
                from facebook_camofox_client.domain_cursors.models import Cursor
                new_cursor = Cursor(
                    cursor_key=self.CURSOR_KEY,
                    action_type="posts.listen",
                    account_id=envelope.account_id,
                    scope_key=scope_key,
                    last_post_id=newest_post_id or "",
                    watermark=newest_watermark,
                )
                await self.cursor_repo.save(new_cursor)

            is_degraded = scroll_phase_dropped > 0 or degraded_count > 0 or rejected_count > 0
            await self.event_emitter.emit(
                "posts.listen_completed",
                {
                    "action_id": envelope.action_id,
                    "new_count": len(new_records),
                    "degraded_count": degraded_count,
                    "rejected_count": rejected_count,
                    "scroll_phase_dropped": scroll_phase_dropped,
                    "degraded": is_degraded,
                    "cursor_advanced": cursor_advanced,
                },
                dedupe_key=f"{envelope.action_id}-completed",
            )

            return PostsListenOutput(
                new_posts=[r.model_dump() for r in new_records],
                cursor_advanced=cursor_advanced,
            )

        except Exception as exc:
            await self.event_emitter.emit(
                "posts.listen_failed",
                {"action_id": envelope.action_id, "reason": str(exc)},
                dedupe_key=f"{envelope.action_id}-failed",
            )
            raise

        finally:
            await self.session_manager.release(session)
