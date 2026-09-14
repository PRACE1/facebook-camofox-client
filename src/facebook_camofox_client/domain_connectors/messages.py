"""Twenty messages read client (read-only).

Why read-only: Twenty's messages object is email-sync managed
(messageThread/participants relations, 290 live associations).
Freeform POSTs would pollute real mail history, so writes stay
disabled until the team approves an explicit send path with guards.
"""
from __future__ import annotations

import os

import httpx

TIMEOUT_SECONDS = 15
OBJECT = "messages"


def _base_url() -> str:
    return (os.getenv("TWENTY_BASE_URL") or "").rstrip("/")


def _headers(api_key: str | None = None) -> dict:
    key = api_key if api_key is not None else (os.getenv("TWENTY_API_KEY") or "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _extract_rows(payload: dict) -> list[dict]:
    data = (payload or {}).get("data") or {}
    if isinstance(data, list):
        return data
    for key in (OBJECT, "message"):
        rows = data.get(key, [])
        if isinstance(rows, dict):
            rows = [rows]
        if rows:
            return rows if isinstance(rows, list) else []
    for value in data.values():  # verb-prefixed e.g. createMessage
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
    return []


class MessagesClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else (os.getenv("TWENTY_API_KEY") or "")

    def _headers(self) -> dict:
        return _headers(self.api_key)

    async def list_messages(self, limit: int = 20) -> tuple[list[dict], int | None]:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{self.base_url}/{OBJECT}",
                params={"limit": limit},
                headers=self._headers(),
            )
            resp.raise_for_status()
            payload = resp.json()
            return _extract_rows(payload), payload.get("totalCount")

    async def get_message(self, message_id: str) -> dict | None:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{self.base_url}/{OBJECT}/{message_id}",
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            rows = _extract_rows(resp.json())
            return rows[0] if rows else None

    async def create_message(self, fields: dict) -> dict:
        raise ValueError(
            "messages writes disabled: Twenty messages are email-sync managed; "
            "team approval + guards required before any POST"
        )
