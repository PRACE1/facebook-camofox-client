"""Continuous multi-group polling with durable commit."""
import asyncio
import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, "src")

from facebook_camofox_client.domain_camofox.session_manager import CamofoxSessionManager
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_records.normalization import PostNormalizer
from facebook_camofox_client.domain_connectors.openmagpie import FacebookCamofoxConnector
from facebook_camofox_client.domain_records.models import NormalizedPostRecord
from facebook_camofox_client.domain_cursors.repository import CursorRepository
from facebook_camofox_client.domain_cursors.models import Cursor

DB_PATH = Path("crm_mock.db")

# --- Durable SQLite Cursor Repository ---
class SqliteCursorRepository(CursorRepository):
    def __init__(self, db_path: Path):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cursors (
                    cursor_key TEXT,
                    account_id TEXT,
                    scope_key TEXT,
                    action_type TEXT,
                    last_post_id TEXT,
                    watermark TEXT,
                    opaque_cursor TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (cursor_key, account_id, scope_key)
                )
            ''')

    async def load(self, cursor_key: str, account_id: str, scope_key: str) -> Cursor | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('''
                SELECT * FROM cursors 
                WHERE cursor_key = ? AND account_id = ? AND scope_key = ?
            ''', (cursor_key, account_id, scope_key)).fetchone()
            
            if row:
                return Cursor(
                    cursor_key=row['cursor_key'],
                    account_id=row['account_id'],
                    scope_key=row['scope_key'],
                    action_type=row['action_type'],
                    last_post_id=row['last_post_id'],
                    watermark=datetime.fromisoformat(row['watermark']) if row['watermark'] else None,
                    opaque_cursor=row['opaque_cursor'] or "",
                    updated_at=datetime.fromisoformat(row['updated_at'])
                )
        return None

    async def save(self, cursor: Cursor) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO cursors 
                (cursor_key, account_id, scope_key, action_type, last_post_id, watermark, opaque_cursor, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cursor_key, account_id, scope_key) DO UPDATE SET
                    action_type=excluded.action_type,
                    last_post_id=excluded.last_post_id,
                    watermark=excluded.watermark,
                    opaque_cursor=excluded.opaque_cursor,
                    updated_at=excluded.updated_at
            ''', (
                cursor.cursor_key,
                cursor.account_id,
                cursor.scope_key,
                cursor.action_type,
                cursor.last_post_id,
                cursor.watermark.isoformat() if cursor.watermark else None,
                cursor.opaque_cursor,
                cursor.updated_at.isoformat()
            ))


# --- Durable CRM Commit Setup ---
def setup_crm_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                record_id TEXT PRIMARY KEY,
                external_id TEXT,
                group_id TEXT,
                author_name TEXT,
                content TEXT,
                url TEXT,
                occurred_at TEXT,
                committed_at TEXT
            )
        ''')

async def durable_commit(record: NormalizedPostRecord) -> bool:
    """Durable commit into our mocked CRM (SQLite)."""
    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute('''
                INSERT OR IGNORE INTO posts 
                (record_id, external_id, group_id, author_name, content, url, occurred_at, committed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.record_id,
                record.external_id,
                getattr(record, "group_id", ""),
                record.author.name if record.author else "",
                record.content,
                record.url,
                record.occurred_at.isoformat() if record.occurred_at else "",
                datetime.utcnow().isoformat()
            ))
            print(f"[COMMIT] Durably saved post {record.external_id} to CRM.")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to commit {record.external_id}: {e}")
            return False

# --- Configuration ---
GROUPS = [
    "305056891435827", # Testing group
    "2128481785219446", # Galway House Hunting For Sound People
    "3001705680075695", # All Things Galway
]

async def main():
    setup_crm_db()
    
    # We will instantiate the connector
    manager = CamofoxSessionManager()
    cursors = SqliteCursorRepository(DB_PATH) 
    events = InMemoryEventEmitter()
    
    # Optional override from env
    account_id = os.environ.get("FACEBOOK_ACCOUNT_ID", "listen-group")
    
    connector = FacebookCamofoxConnector(
        session_manager=manager,
        cursor_repo=cursors,
        emitter=events,
        normalizer=PostNormalizer(),
        commit=durable_commit
    )
    
    print(f"Starting continuous polling for {len(GROUPS)} groups...")
    
    # We'll just run forever, polling sequentially. 
    while True:
        for group_id in GROUPS:
            print(f"\n--- Polling group {group_id} ---")
            spec = {"group_id": group_id, "limit": 5, "account_id": account_id}
            
            try:
                async for post in connector.poll(spec):
                    print(f"Yielded to caller: {post['external_id']}")
            except Exception as e:
                print(f"[ERROR] Polling group {group_id} failed: {e}")
            
            # Short sleep between groups
            await asyncio.sleep(5)
            
        print("\nSleeping before next round...")
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
