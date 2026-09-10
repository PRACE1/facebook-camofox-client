"""Live dry-run of GroupPostAction — fills composer, NO post.

Ground-truth discovery: composer selectors are UNVERIFIED for this group.
Inspect artifacts/receipts/composer_filled_*.html after the run and pin them.

Run from repo root (CMD):
    set CAMOFOX_STORAGE_STATE_LISTEN_GROUP=%USERPROFILE%\\fb_cookies_playwright.json
    python scripts\\run_group_post_dryrun.py
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "src")

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups.post import GroupPostAction
from facebook_camofox_client.domain_marketplace.receipts import ReceiptStore

COOKIE_FILE = Path(os.getenv(
    "CAMOFOX_STORAGE_STATE_LISTEN_GROUP",
    str(Path.home() / "fb_cookies_playwright.json"),
))
GROUP_ID = os.getenv("GROUP_POST_GROUP_ID", "305056891435827")


async def main() -> int:
    if not COOKIE_FILE.exists():
        print(f"Cookie file not found at {COOKIE_FILE}")
        return 2
    manager = CamofoxSessionManager()
    real_acquire = manager.acquire

    async def acquire(account_id, **kwargs):
        kwargs.setdefault("storage_state_path", str(COOKIE_FILE))
        return await real_acquire(account_id, **kwargs)

    manager.acquire = acquire  # type: ignore[method-assign]
    action = GroupPostAction(manager, InMemoryEventEmitter(), ReceiptStore())
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    env = ActionEnvelope(
        action_id=f"groupdry-{ts}", action_type=GroupPostAction.ACTION_TYPE,
        account_id="group-dryrun",
        input={"group_id": GROUP_ID,
               "message": "Dry-run probe — please ignore (testing posting pipeline).",
               "image_paths": [], "dry_run": True},
        idempotency_key=f"groupdry-{ts}",
    )
    out = await action.execute(env)
    print(f"posted={out['posted']} (dry-run, nothing posted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
