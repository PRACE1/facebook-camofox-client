import asyncio
import json
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, "src")

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_cursors.repository import InMemoryCursorRepository
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_posts.listen import PostsListenAction
from facebook_camofox_client.domain_records.normalization import PostNormalizer

# ---------- SQLite Commit ----------
DB_PATH = Path.home() / "facebook_posts.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            record_id TEXT PRIMARY KEY,
            external_id TEXT,
            group_id TEXT,
            content TEXT,
            url TEXT,
            author_id TEXT,
            author_name TEXT,
            occurred_at TEXT,
            collected_at TEXT,
            raw_json TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_group_ext ON posts(group_id, external_id)")
    conn.commit()
    conn.close()

def commit_post(record):
    # record is a NormalizedPostRecord – use attribute access
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM posts WHERE record_id = ?", (record.record_id,))
    if cur.fetchone():
        conn.close()
        return False
    cur.execute("""
        INSERT INTO posts (
            record_id, external_id, group_id, content, url,
            author_id, author_name, occurred_at, collected_at, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.record_id,
        record.external_id,
        record.group_id,
        record.content,
        record.url,
        record.author.get("id", "") if record.author else "",
        record.author.get("name", "") if record.author else "",
        str(record.occurred_at) if record.occurred_at else None,
        datetime.now(timezone.utc).isoformat(),
        json.dumps(record.raw_extraction) if hasattr(record, "raw_extraction") else "{}"
    ))
    conn.commit()
    conn.close()
    return True

# ---------- Main Loop ----------
async def main():
    init_db()

    GROUP_IDS = os.getenv("FACEBOOK_GROUP_IDS", "305056891435827").split(",")
    ACCOUNT_ID = os.getenv("FACEBOOK_ACCOUNT_ID", "listen-group")
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

    cursors = InMemoryCursorRepository()
    normalizer = PostNormalizer()

    print(f"Polling groups: {GROUP_IDS}")
    print(f"Commit DB: {DB_PATH}")
    print(f"Poll interval: {POLL_INTERVAL}s")

    while True:
        for gid in GROUP_IDS:
            gid = gid.strip()
            if not gid:
                continue

            print(f"\n[{datetime.now(timezone.utc)}] Listening to group {gid}...")

            events = InMemoryEventEmitter()
            manager = CamofoxSessionManager()

            async def commit(record):
                return commit_post(record)

            action = PostsListenAction(
                manager, cursors, normalizer, events, commit=commit
            )

            envelope = ActionEnvelope(
                action_id=f"live-posts-listen-{gid}",
                action_type="posts.listen",
                account_id=ACCOUNT_ID,
                input={"group_id": gid, "terms": [], "limit": 3},
                idempotency_key=f"live-posts-listen-{gid}",
            )

            try:
                result = await action.execute(envelope)
                new_count = 0
                for e in events.events:
                    if e.event_type == "posts.listen_completed":
                        new_count = e.payload.get("new_count", 0)
                        break
                print(f"  -> {new_count} new posts committed.")
                if hasattr(result, "degraded") and result.degraded:
                    print(f"  (degraded: {result.degraded})")
            except Exception as e:
                print(f"  !! Error: {e}")

        print(f"Sleeping {POLL_INTERVAL}s before next round...")
        await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())