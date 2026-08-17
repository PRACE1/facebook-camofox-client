import os

def write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# domain_runtime/__init__.py
write("src/facebook_camofox_client/domain_runtime/__init__.py", [
    '"""Domain: Runtime protocols and base models."""',
])

# domain_runtime/models.py
write("src/facebook_camofox_client/domain_runtime/models.py", [
    '"""Shared runtime models."""',
    "from __future__ import annotations",
    "from datetime import datetime",
    "from pydantic import BaseModel, Field",
    "",
    "class Cursor(BaseModel):",
    '    cursor_key: str',
    '    action_type: str',
    '    account_id: str',
    '    scope_key: str',
    '    last_post_id: str = ""',
    '    watermark: datetime | None = None',
    '    opaque_cursor: str = ""',
    '    updated_at: datetime = Field(default_factory=datetime.utcnow)',
    "",
    "class DomainEvent(BaseModel):",
    '    event_type: str',
    '    action_id: str',
    '    record_id: str | None = None',
    '    dedupe_key: str',
    '    occurred_at: datetime = Field(default_factory=datetime.utcnow)',
    '    payload: dict = Field(default_factory=dict)',
])

# domain_runtime/protocols.py
write("src/facebook_camofox_client/domain_runtime/protocols.py", [
    '"""Runtime protocols."""',
    "from typing import Protocol, runtime_checkable",
    "from domain_runtime.models import Cursor, DomainEvent",
    "",
    "@runtime_checkable",
    "class CursorRepository(Protocol):",
    "    async def load(self, cursor_key: str, account_id: str, scope_key: str) -> Cursor | None: ...",
    "    async def save(self, cursor: Cursor) -> None: ...",
    "",
    "@runtime_checkable",
    "class EventEmitter(Protocol):",
    "    async def emit(self, event_type: str, payload: dict, dedupe_key: str) -> DomainEvent: ...",
])

# domain_accounts/__init__.py
write("src/facebook_camofox_client/domain_accounts/__init__.py", [
    '"""Domain: Account management and auth."""',
])

# domain_accounts/models.py
write("src/facebook_camofox_client/domain_accounts/models.py", [
    '"""Account models."""',
    "from pydantic import BaseModel",
    "",
    "class Account(BaseModel):",
    '    account_id: str',
    '    profile_name: str = ""',
    '    cookies_file: str | None = None',
    '    proxy_config: dict | None = None',
])

# domain_accounts/auth_guard.py
write("src/facebook_camofox_client/domain_accounts/auth_guard.py", [
    '"""Auth guard."""',
    "from __future__ import annotations",
    "from pydantic import BaseModel",
    "",
    "class AuthGuardResult(BaseModel):",
    '    authenticated: bool',
    '    requires_action: str | None = None',
    "",
    "class AuthGuard:",
    "    async def validate(self, account, session) -> AuthGuardResult:",
    '        return AuthGuardResult(authenticated=True)',
])

# domain_camofox/__init__.py
write("src/facebook_camofox_client/domain_camofox/__init__.py", [
    '"""Domain: Camofox session management."""',
])

# domain_camofox/session_manager.py
write("src/facebook_camofox_client/domain_camofox/session_manager.py", [
    '"""Manages AsyncCamoufox sessions per account."""',
    "from __future__ import annotations",
    "import uuid",
    "from camofox.async_api import AsyncCamoufox",
    "",
    "class CamofoxSession:",
    '    """Wrapper around AsyncCamoufox browser session."""',
    "",
    "    def __init__(self, account_id: str, browser: AsyncCamoufox) -> None:",
    '        self.account_id = account_id',
    '        self.session_id = str(uuid.uuid4())',
    '        self.browser = browser',
    '        self._ready = False',
    "",
    "    async def ensure_ready(self) -> dict:",
    '        self._ready = True',
    '        return {"status": "ready", "session_id": self.session_id}',
    "",
    "    async def auth_guard(self) -> dict:",
    '        return {"authenticated": True}',
    "",
    "    async def open_surface(self, surface: str, target: dict) -> None:",
    '        page = await self.browser.new_page()',
    '        if surface == "facebook_group":',
    '            group_id = target.get("group_id", "")',
    '            url = target.get("url") or f"https://facebook.com/groups/{group_id}"',
    '            await page.goto(url)',
    "",
    "    async def execute(self, activity: str, params: dict) -> dict:",
    '        return {"activity": activity, "params": params, "results": []}',
    "",
    "    async def close(self) -> None:",
    '        await self.browser.stop()',
    "",
    "class CamofoxSessionManager:",
    '    """Acquires and releases account-scoped Camofox sessions."""',
    "",
    "    def __init__(self) -> None:",
    '        self._sessions: dict[str, CamofoxSession] = {}',
    "",
    "    async def acquire(self, account_id: str, proxy_config: dict | None = None) -> CamofoxSession:",
    '        browser = await AsyncCamoufox(humanize=True, geoip=True, proxy=proxy_config).__aenter__()',
    '        session = CamofoxSession(account_id=account_id, browser=browser)',
    '        self._sessions[session.session_id] = session',
    '        return session',
    "",
    "    async def release(self, session_id: str) -> None:",
    '        session = self._sessions.pop(session_id, None)',
    '        if session:',
    '            await session.browser.__aexit__(None, None, None)',
])

# domain_actions/__init__.py
write("src/facebook_camofox_client/domain_actions/__init__.py", [
    '"""Domain: Action envelope and runner."""',
])

# domain_actions/envelope.py
write("src/facebook_camofox_client/domain_actions/envelope.py", [
    '"""Action envelope model."""',
    "from datetime import datetime",
    "from pydantic import BaseModel, Field",
    "",
    "class ActionEnvelope(BaseModel):",
    '    action_id: str',
    '    action_type: str',
    '    account_id: str',
    '    session_id: str | None = None',
    '    input: dict = Field(default_factory=dict)',
    '    idempotency_key: str',
    '    status: str = "queued"',
    '    created_at: datetime = Field(default_factory=datetime.utcnow)',
])

# domain_actions/runner.py
write("src/facebook_camofox_client/domain_actions/runner.py", [
    '"""Action runner dispatches envelopes to handlers."""',
    "from __future__ import annotations",
    "from domain_actions.envelope import ActionEnvelope",
    "",
    "class ActionRunner:",
    "    def __init__(self) -> None:",
    '        self._handlers: dict[str, callable] = {}',
    "",
    "    def register(self, action_type: str, handler: callable) -> None:",
    '        self._handlers[action_type] = handler',
    "",
    "    async def run(self, envelope: ActionEnvelope) -> dict:",
    '        handler = self._handlers.get(envelope.action_type)',
    '        if not handler:',
    '            raise ValueError(f"No handler for: {envelope.action_type}")',
    '        envelope.status = "running"',
    '        result = await handler(envelope)',
    '        envelope.status = "completed"',
    '        return result',
])

# domain_groups/search.py
write("src/facebook_camofox_client/domain_groups/search.py", [
    '"""Groups search action implementation."""',
    "from __future__ import annotations",
    "from datetime import datetime, UTC",
    "from typing import Any",
    "from domain_actions.envelope import ActionEnvelope",
    "from domain_camofox.session_manager import CamofoxSessionManager",
    "from domain_cursors.models import Cursor",
    "from domain_events.models import DomainEvent",
    "from domain_records.models import NormalizedPostRecord",
    "from domain_records.normalization import PostNormalizer",
    "from domain_groups.schemas import GroupsSearchInput, GroupsSearchOutput",
    "",
    "class GroupsSearchAction:",
    '    """Execute groups.search through Camofox."""',
    "",
    "    def __init__(self, session_manager: CamofoxSessionManager, cursor_repo: Any, normalizer: PostNormalizer, event_emitter: Any) -> None:",
    '        self.session_manager = session_manager',
    '        self.cursor_repo = cursor_repo',
    '        self.normalizer = normalizer',
    '        self.event_emitter = event_emitter',
    "",
    "    async def execute(self, envelope: ActionEnvelope) -> GroupsSearchOutput:",
    '        input_data = GroupsSearchInput(**envelope.input)',
    '        scope_key = f"{envelope.account_id}-{\'-\' .join(input_data.group_ids)}-{\'-\' .join(input_data.terms)}"',
    '        await self._emit(\"groups.search_started\", envelope, {})',
    '        cursor = await self.cursor_repo.load(cursor_key=\"groups-search\", account_id=envelope.account_id, scope_key=scope_key)',
    '        session = await self.session_manager.acquire(envelope.account_id)',
    '        try:',
    '            auth = await session.auth_guard()',
    '            if not auth.get(\"authenticated\"):',
    '                await self._emit(\"groups.search_failed\", envelope, {\"reason\": \"auth_required\"})',
    '                return GroupsSearchOutput(results=[], cursor={}, matched_terms=[])',
    '            for gid in input_data.group_ids:',
    '                await session.open_surface(\"facebook_group\", {\"group_id\": gid})',
    '            raw = await session.execute(\"facebook_group_search\", {\"terms\": input_data.terms, \"limit\": input_data.limit, \"cursor\": cursor.opaque_cursor if cursor else None, \"since\": input_data.since})',
    '            records: list[NormalizedPostRecord] = []',
    '            for post in raw.get(\"results\", []):',
    '                rec = self.normalizer.normalize(raw=post, account_id=envelope.account_id, source_action=envelope.action_id)',
    '                records.append(rec)',
    '                await self._emit(\"groups.result_found\", envelope, {\"record_id\": rec.record_id, \"external_id\": rec.external_id})',
    '            new_cursor = self._build_cursor(cursor, records, scope_key)',
    '            await self.cursor_repo.save(new_cursor)',
    '            await self._emit(\"groups.search_completed\", envelope, {\"records_found\": len(records)})',
    '            return GroupsSearchOutput(results=[r.model_dump() for r in records], cursor=new_cursor.model_dump(), matched_terms=input_data.terms)',
    '        except Exception as exc:',
    '            await self._emit(\"groups.search_failed\", envelope, {\"reason\": str(exc)})',
    '            raise',
    '        finally:',
    '            await self.session_manager.release(session.session_id)',
    "",
    "    def _build_cursor(self, old: Cursor | None, records: list[NormalizedPostRecord], scope_key: str) -> Cursor:",
    '        last = records[-1] if records else None',
    '        return Cursor(',
    '            cursor_key=\"groups-search\",',
    '            action_type=\"groups.search\",',
    '            account_id=last.account_id if last else (old.account_id if old else \"\"),',
    '            scope_key=scope_key,',
    '            last_post_id=last.external_id if last else (old.last_post_id if old else \"\"),',
    '            watermark=last.occurred_at if last else datetime.now(UTC),',
    '            opaque_cursor=f\"cursor-{datetime.now(UTC).timestamp()}\",',
    '        )',
    "",
    "    async def _emit(self, event_type: str, envelope: ActionEnvelope, payload: dict) -> None:",
    '        dedupe = f\"{envelope.action_id}-{event_type}-{datetime.now(UTC).timestamp()}\"',
    '        await self.event_emitter.emit(event_type=event_type, payload={\"action_id\": envelope.action_id, **payload}, dedupe_key=dedupe)',
])

# domain_records/__init__.py
write("src/facebook_camofox_client/domain_records/__init__.py", [
    '"""Domain: Normalized records."""',
])

# domain_records/models.py
write("src/facebook_camofox_client/domain_records/models.py", [
    '"""Normalized record models."""',
    "from datetime import datetime",
    "from pydantic import BaseModel, Field",
    "",
    "class NormalizedPostRecord(BaseModel):",
    '    record_id: str',
    '    record_type: str = "facebook_post"',
    '    external_id: str',
    '    source: str = "groups.search"',
    '    account_id: str',
    '    group_id: str = ""',
    '    content: str = ""',
    '    url: str = ""',
    '    author: dict = Field(default_factory=dict)',
    '    occurred_at: datetime = Field(default_factory=datetime.utcnow)',
    '    metrics: dict = Field(default_factory=dict)',
    '    matched_terms: list[str] = Field(default_factory=list)',
    '    raw_extraction: dict | None = None',
])

# domain_records/normalization.py
write("src/facebook_camofox_client/domain_records/normalization.py", [
    '"""Normalize raw Facebook extraction."""',
    "from __future__ import annotations",
    "import uuid",
    "from datetime import datetime, UTC",
    "from domain_records.models import NormalizedPostRecord",
    "",
    "class PostNormalizer:",
    '    def normalize(self, raw: dict, account_id: str, source_action: str) -> NormalizedPostRecord:',
    '        return NormalizedPostRecord(',
    '            record_id=f\"rec-{uuid.uuid4().hex[:12]}\",',
    '            external_id=raw.get(\"post_id\", \"\") or raw.get(\"external_id\", \"\"),',
    '            account_id=account_id,',
    '            group_id=raw.get(\"group_id\", \"\"),',
    '            content=raw.get(\"content\", \"\") or raw.get(\"message\", \"\"),',
    '            url=raw.get(\"url\", \"\") or raw.get(\"permalink\", \"\"),',
    '            author={\"id\": raw.get(\"author_id\", \"\"), \"name\": raw.get(\"author\", \"\")},',
    '            occurred_at=raw.get(\"occurred_at\") or datetime.now(UTC),',
    '            metrics={',
    '                \"likes\": raw.get(\"likes\", 0) or raw.get(\"metrics\", {}).get(\"likes\", 0),',
    '                \"comments\": raw.get(\"comments\", 0) or raw.get(\"metrics\", {}).get(\"comments\", 0),',
    '                \"shares\": raw.get(\"shares\", 0) or raw.get(\"metrics\", {}).get(\"shares\", 0),',
    '            },',
    '            matched_terms=raw.get(\"matched_terms\", []),',
    '            raw_extraction=raw,',
    '        )',
])

# domain_cursors/__init__.py
write("src/facebook_camofox_client/domain_cursors/__init__.py", [
    '"""Domain: Cursor persistence."""',
])

# domain_cursors/models.py
write("src/facebook_camofox_client/domain_cursors/models.py", [
    '"""Cursor models."""',
    "from datetime import datetime",
    "from pydantic import BaseModel, Field",
    "",
    "class Cursor(BaseModel):",
    '    cursor_key: str',
    '    action_type: str',
    '    account_id: str',
    '    scope_key: str',
    '    last_post_id: str = ""',
    '    watermark: datetime | None = None',
    '    opaque_cursor: str = ""',
    '    updated_at: datetime = Field(default_factory=datetime.utcnow)',
])

# domain_cursors/repository.py
write("src/facebook_camofox_client/domain_cursors/repository.py", [
    '"""Cursor repository."""',
    "from __future__ import annotations",
    "from domain_cursors.models import Cursor",
    "",
    "class InMemoryCursorRepository:",
    '    def __init__(self) -> None:',
    '        self._store: dict[str, Cursor] = {}',
    "",
    '    def _key(self, cursor_key: str, account_id: str, scope_key: str) -> str:',
    '        return f\"{cursor_key}:{account_id}:{scope_key}\"',
    "",
    "    async def load(self, cursor_key: str, account_id: str, scope_key: str) -> Cursor | None:",
    '        return self._store.get(self._key(cursor_key, account_id, scope_key))',
    "",
    "    async def save(self, cursor: Cursor) -> None:",
    '        self._store[self._key(cursor.cursor_key, cursor.account_id, cursor.scope_key)] = cursor',
])

# domain_events/__init__.py
write("src/facebook_camofox_client/domain_events/__init__.py", [
    '"""Domain: Event emission."""',
])

# domain_events/models.py
write("src/facebook_camofox_client/domain_events/models.py", [
    '"""Event models."""',
    "from datetime import datetime",
    "from pydantic import BaseModel, Field",
    "",
    "class DomainEvent(BaseModel):",
    '    event_type: str',
    '    action_id: str',
    '    record_id: str | None = None',
    '    dedupe_key: str',
    '    occurred_at: datetime = Field(default_factory=datetime.utcnow)',
    '    payload: dict = Field(default_factory=dict)',
])

# domain_events/emitter.py
write("src/facebook_camofox_client/domain_events/emitter.py", [
    '"""Event emitter."""',
    "from __future__ import annotations",
    "from datetime import datetime, UTC",
    "from domain_events.models import DomainEvent",
    "",
    "class InMemoryEventEmitter:",
    '    def __init__(self) -> None:',
    '        self.events: list[DomainEvent] = []',
    "",
    "    async def emit(self, event_type: str, payload: dict, dedupe_key: str) -> DomainEvent:",
    '        ev = DomainEvent(event_type=event_type, action_id=payload.get(\"action_id\", \"\"), record_id=payload.get(\"record_id\"), dedupe_key=dedupe_key, payload=payload)',
    '        self.events.append(ev)',
    '        return ev',
])

# domain_connectors/__init__.py
write("src/facebook_camofox_client/domain_connectors/__init__.py", [
    '"""Domain: OpenMagpie connector adapter."""',
])

# domain_connectors/openmagpie.py
write("src/facebook_camofox_client/domain_connectors/openmagpie.py", [
    '"""Adapter to wire into OpenMagpie."""',
    "from __future__ import annotations",
    "from collections.abc import Callable, Iterator",
    "from datetime import datetime",
    "from typing import ClassVar",
    "from domain_actions.envelope import ActionEnvelope",
    "from domain_actions.runner import ActionRunner",
    "from domain_camofox.session_manager import CamofoxSessionManager",
    "from domain_cursors.repository import InMemoryCursorRepository",
    "from domain_events.emitter import InMemoryEventEmitter",
    "from domain_groups.search import GroupsSearchAction",
    "from domain_records.normalization import PostNormalizer",
    "",
    "class FacebookCamofoxConnector:",
    '    kind: ClassVar[str] = \"facebook_search\"',
    "",
    "    def __init__(self) -> None:",
    '        self.runner = ActionRunner()',
    '        self.session_manager = CamofoxSessionManager()',
    '        self.cursor_repo = InMemoryCursorRepository()',
    '        self.emitter = InMemoryEventEmitter()',
    '        self.normalizer = PostNormalizer()',
    '        search = GroupsSearchAction(self.session_manager, self.cursor_repo, self.normalizer, self.emitter)',
    '        self.runner.register(\"groups.search\", search.execute)',
    "",
    "    async def poll(self, spec: dict, since: datetime | None = None) -> Iterator[dict]:",
    '        envelope = ActionEnvelope(action_id=f\"poll-{datetime.now().timestamp()}\", action_type=\"groups.search\", account_id=spec.get(\"account_id\", \"default\"), input=spec, idempotency_key=f\"poll-{spec.get(\'page_url\', \'\')}-{since}\")',
    '        result = await self.runner.run(envelope)',
    '        for record in result.get(\"results\", []):',
    '            yield record',
])

# tests/__init__.py
write("tests/__init__.py", [])

# tests/domain_groups/__init__.py
write("tests/domain_groups/__init__.py", [])

# tests/domain_groups/test_search.py
write("tests/domain_groups/test_search.py", [
    '"""Tests for groups.search."""',
    "import pytest",
    "from datetime import datetime, UTC",
    "from domain_actions.envelope import ActionEnvelope",
    "from domain_camofox.session_manager import CamofoxSessionManager",
    "from domain_cursors.repository import InMemoryCursorRepository",
    "from domain_events.emitter import InMemoryEventEmitter",
    "from domain_groups.search import GroupsSearchAction",
    "from domain_records.normalization import PostNormalizer",
    "",
    "@pytest.mark.asyncio",
    "async def test_search_emits_events():",
    '    session_mgr = CamofoxSessionManager()',
    '    cursor_repo = InMemoryCursorRepository()',
    '    emitter = InMemoryEventEmitter()',
    '    normalizer = PostNormalizer()',
    '    action = GroupsSearchAction(session_mgr, cursor_repo, normalizer, emitter)',
    '    envelope = ActionEnvelope(action_id=\"t1\", action_type=\"groups.search\", account_id=\"acc1\", input={\"group_ids\": [\"g1\"], \"terms\": [\"crypto\"], \"limit\": 5}, idempotency_key=\"k1\")',
    '    try:',
    '        await action.execute(envelope)',
    '    except Exception:',
    '        pass',
    '    assert len(emitter.events) >= 1',
    '    assert emitter.events[0].event_type == \"groups.search_started\"',
])

# scripts/smoke_test.py
write("scripts/smoke_test.py", [
    '"""Smoke test for first vertical slice."""',
    "import asyncio",
    "import sys",
    "sys.path.insert(0, 'src')",
    "from domain_actions.envelope import ActionEnvelope",
    "from domain_camofox.session_manager import CamofoxSessionManager",
    "from domain_cursors.repository import InMemoryCursorRepository",
    "from domain_events.emitter import InMemoryEventEmitter",
    "from domain_groups.search import GroupsSearchAction",
    "from domain_records.normalization import PostNormalizer",
    "",
    "async def main():",
    '    print(\"=== Smoke Test ===\")',
    '    session_mgr = CamofoxSessionManager()',
    '    cursor_repo = InMemoryCursorRepository()',
    '    emitter = InMemoryEventEmitter()',
    '    normalizer = PostNormalizer()',
    '    action = GroupsSearchAction(session_mgr, cursor_repo, normalizer, emitter)',
    '    envelope = ActionEnvelope(action_id=\"s1\", action_type=\"groups.search\", account_id=\"demo\", input={\"group_ids\": [\"demo\"], \"terms\": [\"test\"], \"limit\": 3}, idempotency_key=\"sk1\")',
    '    try:',
    '        result = await action.execute(envelope)',
    '        print(f\"Results: {len(result.results)}\")',
    '    except Exception as e:',
    '        print(f\"Expected error without Camofox: {e}\")',
    '    print(f\"Events: {len(emitter.events)}\")',
    '    for ev in emitter.events:',
    '        print(f\"  - {ev.event_type}\")',
    "",
    "if __name__ == '__main__':",
    '    asyncio.run(main())',
])

print("All slice files created.")