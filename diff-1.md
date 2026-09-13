diff --git a/src/facebook_camofox_client/domain_connectors/openmagpie.py b/src/facebook_camofox_client/domain_connectors/openmagpie.py
--- a/src/facebook_camofox_client/domain_connectors/openmagpie.py
+++ b/src/facebook_camofox_client/domain_connectors/openmagpie.py
@@
-from collections.abc import Iterator
+from collections.abc import AsyncIterator, Awaitable, Callable
@@
 from facebook_camofox_client.domain_posts.listen import PostsListenAction
+from facebook_camofox_client.domain_records.models import NormalizedPostRecord
@@
-class FacebookCamofoxConnector:
+CommitCallback = Callable[[NormalizedPostRecord], Awaitable[bool]]
+
+
+async def _missing_commit(_: NormalizedPostRecord) -> bool:
+    raise RuntimeError(
+        "posts.listen requires a durable commit(payload) callback before cursor advancement"
+    )
+
+
+class FacebookCamofoxConnector:
@@
         emitter: Any | None = None,
         normalizer: Any | None = None,
+        commit: CommitCallback | None = None,
@@
         self.normalizer = normalizer or PostNormalizer()
+        self.commit = commit or _missing_commit
@@
-        listen = PostsListenAction(self.session_manager, self.cursor_repo, self.normalizer, self.emitter)
+        listen = PostsListenAction(
+            self.session_manager,
+            self.cursor_repo,
+            self.normalizer,
+            self.emitter,
+            commit=self.commit,
+        )
@@
-    async def poll(self, spec: dict, since: datetime | None = None) -> Iterator[dict]:
+    async def poll(self, spec: dict, since: datetime | None = None) -> AsyncIterator[dict]:
@@
-    async def listen(self, spec: dict) -> Iterator[dict]:
+    async def listen(self, spec: dict) -> AsyncIterator[dict]:
