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

# Non-target content (per data-hygiene boundary): synthetic probe ids,
# mock prefixes, and records unlinked to a real offer never leave this box.
_MOCK_PREFIXES = ("test", "mock", "probe", "demo", "fake", "sample")


def validate_outbound(fields: dict) -> None:
    """Boundary guard: only verified live listings linked to a real offer
    may be persisted to Twenty. Raises ValueError otherwise — before any
    network request is made."""
    import re

    listing_id = str(fields.get("listingId") or "")
    if not re.fullmatch(r"\d{10,20}", listing_id):
        raise ValueError(f"refusing non-Facebook listingId: {listing_id!r}")
    offer_id = str(fields.get("offerId") or fields.get("offer_id") or "")
    if not offer_id:
        raise ValueError("refusing unlinked record: offerId required")
    if offer_id.lower().startswith(_MOCK_PREFIXES):
        raise ValueError(f"refusing mock offerId: {offer_id!r}")
    if listing_id.lower().startswith(_MOCK_PREFIXES):
        raise ValueError(f"refusing mock listingId: {listing_id!r}")


def _base_url() -> str:
    return (os.getenv("TWENTY_BASE_URL") or "").rstrip("/")


def _headers() -> dict:
    key = os.getenv("TWENTY_API_KEY") or ""
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _extract_rows(payload: dict) -> list[dict]:
    data = (payload or {}).get("data") or {}
    if isinstance(data, list):
        return data
    for key in (OBJECT, "agencyListing"):
        rows = data.get(key, [])
        if isinstance(rows, dict):  # POST/PATCH nest single verbs (create/updateX)
            rows = [rows]
        if rows:
            return rows if isinstance(rows, list) else []
    for value in data.values():  # e.g. updateAgencyListing / createAgencyListing
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
    return []


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
            rows = _extract_rows(resp.json())
            return rows[0] if rows else {}

    async def upsert_listing(self, fields: dict) -> tuple[dict, bool]:
        """Insert or update by listingId. Returns (row, created?)."""
        validate_outbound(fields)
        listing_id = fields.get("listingId")
        existing = await self.find_by_listing_id(str(listing_id))
        if existing and existing.get("id"):
            return await self.update_row(existing["id"], fields), False
        return await self.create_row(fields), True
