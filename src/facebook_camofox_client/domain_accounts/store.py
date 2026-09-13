"""Social Accounts store — saved Facebook accounts + cookies (SQLite).

One row per account: label, platform, raw CRM cookie JSON. Sessions resolve
cookies by account_id so callers stop passing blobs per request.

Security note: cookie values are secrets. They rest here as plaintext JSON
(file permissions are the only guard — same as the fb_cookies*.json files
already on this box). Field-level encryption is the flagged follow-up;
list/get-metadata NEVER return cookie values (see metadata()).
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS social_accounts (
  account_id TEXT PRIMARY KEY,
  label TEXT NOT NULL DEFAULT '',
  platform TEXT NOT NULL DEFAULT 'facebook',
  cookies_json TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
)
"""


class SocialAccountStore:
    def __init__(self, db_path: str | Path = "state/social_accounts.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(SCHEMA)

    def save(self, account_id: str, cookies: list[dict], label: str = "",
             platform: str = "facebook") -> None:
        if not account_id:
            raise ValueError("account_id required")
        if not isinstance(cookies, list) or not cookies:
            raise ValueError("cookies must be a non-empty list")
        now = time.time()
        blob = json.dumps(cookies)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO social_accounts
                   (account_id, label, platform, cookies_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(account_id) DO UPDATE SET
                     label=excluded.label, platform=excluded.platform,
                     cookies_json=excluded.cookies_json, updated_at=excluded.updated_at""",
                (account_id, label, platform, blob, now, now),
            )

    def load_cookies(self, account_id: str) -> list[dict] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT cookies_json FROM social_accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row[0])
            return data if isinstance(data, list) else None
        except (json.JSONDecodeError, TypeError):
            return None

    def metadata(self) -> list[dict]:
        """List accounts WITHOUT cookie values (safe for API responses)."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT account_id, label, platform, updated_at FROM social_accounts"
            ).fetchall()
        return [{"account_id": r[0], "label": r[1], "platform": r[2],
                 "updated_at": r[3]} for r in rows]

    def delete(self, account_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM social_accounts WHERE account_id = ?",
                               (account_id,))
            return cur.rowcount > 0
