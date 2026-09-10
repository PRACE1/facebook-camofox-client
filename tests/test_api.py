"""API tests — TestClient, browser-touching routes monkeypatched."""
from fastapi.testclient import TestClient

from facebook_camofox_client.api import app as app_module
from facebook_camofox_client.domain_marketplace import create as create_mod
from facebook_camofox_client.domain_marketplace import status as status_mod


def _client():
    return TestClient(app_module.app)


async def _fake_create_execute(self, envelope):
    from facebook_camofox_client.domain_marketplace.schemas import MarketplaceCreateOutput
    return MarketplaceCreateOutput(published=False)


async def _fake_status_execute(self, envelope):
    from facebook_camofox_client.domain_marketplace.schemas import MarketplaceStatusOutput
    listing_id = envelope.input["listing_id"]
    return MarketplaceStatusOutput(listing_id=listing_id, listing_url=f"https://x/{listing_id}",
                                   status="active", title="T")


def test_healthz():
    assert _client().get("/healthz").json()["ok"] is True


def test_create_dry_run_route(monkeypatch):
    monkeypatch.setattr(create_mod.MarketplaceCreateAction, "execute", _fake_create_execute)
    r = _client().post("/api/listings", json={
        "account_id": "acc",
        "listing": {"title": "T", "price": "50", "category": "Household", "dry_run": True},
    })
    assert r.status_code == 200 and r.json()["published"] is False


def test_status_route(monkeypatch):
    monkeypatch.setattr(status_mod.MarketplaceStatusAction, "execute", _fake_status_execute)
    r = _client().get("/api/listings/123/status")
    assert r.status_code == 200 and r.json()["status"] == "active"


def test_watchlist_roundtrip():
    c = _client()
    assert c.get("/api/watchlist").json() == []
    r = c.post("/api/watchlist", json={"crm_offer_id": "o1", "account_id": "a",
                                       "current_listing_id": "123", "root_listing_id": "123"})
    assert r.status_code == 201
    assert len(c.get("/api/watchlist").json()) == 1
