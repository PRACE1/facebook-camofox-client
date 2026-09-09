diff --git a/src/facebook_camofox_client/domain_posts/listen.py b/src/facebook_camofox_client/domain_posts/listen.py
--- a/src/facebook_camofox_client/domain_posts/listen.py
+++ b/src/facebook_camofox_client/domain_posts/listen.py
@@
 from __future__ import annotations
 
+from collections.abc import Awaitable, Callable
 from datetime import datetime
@@
 from facebook_camofox_client.domain_records.normalization import RejectedRecord
+from facebook_camofox_client.domain_records.models import NormalizedPostRecord
+
+
+CommitCallback = Callable[[NormalizedPostRecord], Awaitable[bool]]
+
+
+class CommitFailed(RuntimeError):
+    """A normalized record was not durably accepted by the connector."""
@@
-    def __init__(self, session_manager, cursor_repo, normalizer, event_emitter):
+    def __init__(self, session_manager, cursor_repo, normalizer, event_emitter, commit: CommitCallback):
@@
         self.event_emitter = event_emitter
+        self.commit = commit
@@
-                await self.event_emitter.emit(
-                    "posts.new",
-                    {"action_id": envelope.action_id, "record_id": rec.record_id, "post_id": post_id},
-                    dedupe_key=f"{envelope.action_id}-{rec.record_id}",
-                )
-
             cursor_advanced = newest_watermark != watermark or newest_post_id != last_post_id
+
+            # Durability boundary: every record must be accepted by the
+            # connector before the watermark is allowed to move.
+            for record in new_records:
+                committed = await self.commit(record)
+                if committed is not True:
+                    raise CommitFailed(
+                        f"connector rejected record {record.record_id}"
+                    )
+
             if cursor_advanced:
@@
                 )
                 await self.cursor_repo.save(new_cursor)
+
+            for record in new_records:
+                await self.event_emitter.emit(
+                    "posts.new",
+                    {
+                        "action_id": envelope.action_id,
+                        "record_id": record.record_id,
+                        "post_id": record.external_id,
+                    },
+                    dedupe_key=f"{envelope.action_id}-{record.record_id}",
+                )
