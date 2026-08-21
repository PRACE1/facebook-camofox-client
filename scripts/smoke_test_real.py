"""Real smoke test — read-only group navigation."""
import asyncio
import sys
import json
sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_groups.search import GroupsSearchAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer
from facebook_camofox_client.domain_actions.envelope import ActionEnvelope

COOKIES_FILE = r"C:\Users\R5 5600 GT\fb_cookies_playwright.json"
GROUP_ID = "879168359747629"

async def main():
    print("=== Smoke Test: Real Facebook Group ===")

    # Load cookies
    with open(COOKIES_FILE, encoding="utf-8") as f:
        cookies = json.load(f)
    print(f"Cookies loaded: {len(cookies)} entries")

    mgr = CamofoxSessionManager()
    emitter = InMemoryEventEmitter()
    cursor_repo = InMemoryCursorRepository()
    normalizer = PostNormalizer()
    action = GroupsSearchAction(mgr, cursor_repo, normalizer, emitter)

    envelope = ActionEnvelope(
        action_id="smoke-1",
        action_type="groups.search",
        account_id="disposable-test",
        input={"group_ids": [GROUP_ID], "terms": [], "limit": 3},
        idempotency_key="smoke-k1"
    )

    try:
        result = await action.execute(envelope)
        print(f"Records returned: {len(result.results)}")
        print(f"Events emitted: {[e.event_type for e in emitter.events]}")
        for rec in result.results:
            print(f"  - {rec.get('external_id')} | {rec.get('content', '')[:60]}")
    except Exception as e:
        print(f"ERROR: {e}")
        print(f"Events so far: {[e.event_type for e in emitter.events]}")

if __name__ == "__main__":
    asyncio.run(main())