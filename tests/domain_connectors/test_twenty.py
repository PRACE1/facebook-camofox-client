"""Twenty client tests — fake HTTP layer, no credentials, no network."""
import pytest

from facebook_camofox_client.domain_connectors import twenty as twenty_mod
from facebook_camofox_client.domain_connectors.twenty import TwentyClient


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self): return self._payload

    def raise_for_status(self): pass


def _client(handler):
    class Client:
        def __init__(self, *a, **k): pass

        async def __aenter__(self): return self

        async def __aexit__(self, *a): pass

        async def get(self, url, params=None, headers=None):
            return handler("GET", url, params, None)

        async def post(self, url, json=None, headers=None):
            return handler("POST", url, None, json)

        async def patch(self, url, json=None, headers=None):
            return handler("PATCH", url, None, json)

    return Client


@pytest.mark.asyncio
async def test_upsert_creates_when_missing(monkeypatch):
    seen = {}

    def handler(method, url, params, body):
        if method == "GET":
            assert "listingId[eq]:1583545526797714" in (params or {}).get("filter", "")
            return FakeResp({"data": {"agencyListings": []}})
        seen.update(body or {})
        return FakeResp({"data": {"agencyListings": [{"id": "row-1", **(body or {})}]}})

    monkeypatch.setattr(twenty_mod.httpx, "AsyncClient", _client(handler))
    row, created = await TwentyClient("https://x/rest", "k").upsert_listing(
        {"listingId": "1583545526797714", "offerId": "offer-1", "status": "ACTIVE"})
    assert created is True and row["id"] == "row-1" and seen["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_upsert_updates_when_present(monkeypatch):
    patched = {}

    def handler(method, url, params, body):
        if method == "GET":
            return FakeResp({"data": {"agencyListings": [{"id": "row-7"}]}})
        patched["url"] = url
        return FakeResp({"data": {"agencyListings": []}})

    monkeypatch.setattr(twenty_mod.httpx, "AsyncClient", _client(handler))
    row, created = await TwentyClient("https://x/rest", "k").upsert_listing(
        {"listingId": "1583545526797714", "offerId": "offer-1", "status": "SOLD"})
    assert created is False and patched["url"].endswith("/agencyListings/row-7")


@pytest.mark.asyncio
async def test_upsert_requires_listing_id():
    with pytest.raises(ValueError):
        await TwentyClient("https://x/rest", "k").upsert_listing(
            {"status": "ACTIVE", "offerId": "offer-1"})


@pytest.mark.asyncio
async def test_boundary_blocks_non_target():
    from facebook_camofox_client.domain_connectors.twenty import validate_outbound

    with pytest.raises(ValueError):  # short/probe id
        validate_outbound({"listingId": "9", "offerId": "offer-1"})
    with pytest.raises(ValueError):  # unlinked record
        validate_outbound({"listingId": "1583545526797714"})
    with pytest.raises(ValueError):  # mock offer
        validate_outbound({"listingId": "1583545526797714", "offerId": "test-123"})
    validate_outbound({"listingId": "1583545526797714", "offerId": "offer-1"})


@pytest.mark.asyncio
async def test_create_handles_singular_post_shape(monkeypatch):
    def handler(method, url, params, body):
        if method == "GET":
            return FakeResp({"data": {"agencyListings": []}})
        return FakeResp({"data": {"agencyListing": {"id": "row-9"}}})

    monkeypatch.setattr(twenty_mod.httpx, "AsyncClient", _client(handler))
    row, created = await TwentyClient("https://x/rest", "k").upsert_listing(
        {"listingId": "1583545526797714", "offerId": "offer-1"})
    assert created is True and row["id"] == "row-9"


@pytest.mark.asyncio
async def test_update_returns_flat_row(monkeypatch):
    def handler(method, url, params, body):
        if method == "GET":
            return FakeResp({"data": {"agencyListings": [{"id": "row-7"}]}})
        return FakeResp({"data": {"agencyListings": [{"id": "row-7", "status": "SOLD"}]}})

    monkeypatch.setattr(twenty_mod.httpx, "AsyncClient", _client(handler))
    row, created = await TwentyClient("https://x/rest", "k").upsert_listing(
        {"listingId": "1583545526797714", "offerId": "offer-1", "status": "SOLD"})
    assert created is False and row == {"id": "row-7", "status": "SOLD"}
