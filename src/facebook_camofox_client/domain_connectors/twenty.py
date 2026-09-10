"""Twenty CRM REST client for agencyListings rows.

Conventions (from open-twenty-dialer, verified there — NOT re-derived):
base URL already ends in /rest (never append it again), Bearer auth,
{fieldName}Id relation pattern, response shape
{data: {agencyListings: [...]}}, id-ascending pagination (their server
ignores cursors, 200/page cap). Nothing here needs credentials to import;
calls need TWENTY_BASE_URL + TWENTY_API_KEY at runtime.
"""
from __future__ import annotations

import os

import httpx

TIMEOUT_SECONDS = 15
OBJECT = "agencyListings"


def _base_url() -> str:
    return (os.getenv("TWENTY_BASE_URL") or "").rstrip("/")


def _headers() -> dict:
    key = os.getenv("TWENTY_API_KEY") or ""
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _extract_rows(payload: dict) -> list[dict]:
    data = (payload or {}).get("data") or {}
    if isinstance(data, list):
        return data
    rows = data.get(OBJECT, [])
    return rows if isinstance(rows, list) else []


class TwentyClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else (os.getenv("TWENTY_API_KEY") or "")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def find_by_listing_id(self, listing_id: str) -> dict | None:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{self.base_url}/{OBJECT}",
                params={"filter": f"listingId[eq]:{listing_id}", "limit": 1},
                headers=self._headers(),
            )
            resp.raise_for_status()
            rows = _extract_rows(resp.json())
            return rows[0] if rows else None

    async def create_row(self, fields: dict) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{self.base_url}/{OBJECT}", json=fields, headers=self._headers())
            resp.raise_for_status()
            rows = _extract_rows(resp.json())
            return rows[0] if rows else {}

    async def update_row(self, row_id: str, fields: dict) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.patch(
                f"{self.base_url}/{OBJECT}/{row_id}", json=fields,
                headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def upsert_listing(self, fields: dict) -> tuple[dict, bool]:
        """Insert or update by listingId. Returns (row, created?)."""
        listing_id = fields.get("listingId")
        if not listing_id:
            raise ValueError("fields must include listingId")
        existing = await self.find_by_listing_id(str(listing_id))
        if existing and existing.get("id"):
            return await self.update_row(existing["id"], fields), False
        return await self.create_row(fields), True
