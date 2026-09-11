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


def test_action_index_lists_all():
    kinds = _client().get("/api/actions").json()["action_types"]
    for expected in ("posts.listen", "groups.search", "groups.post",
                     "marketplace.create", "marketplace.status"):
        assert expected in kinds


def test_unknown_action_404():
    r = _client().post("/api/actions/nope.notreal",
                       json={"account_id": "a", "input": {}})
    assert r.status_code == 404


def test_generic_posts_listen(monkeypatch):
    from facebook_camofox_client.domain_posts import listen as listen_mod

    real_action = listen_mod.PostsListenAction

    async def fake_execute(self, envelope):
        return {"new_posts": [], "cursor_advanced": False}

    monkeypatch.setattr(real_action, "execute", fake_execute)
    r = _client().post("/api/actions/posts.listen",
                       json={"account_id": "a",
                             "input": {"group_id": "305056891435827"}})
    assert r.status_code == 200
    body = r.json()
    assert body["action_type"] == "posts.listen"
    assert body["result"]["new_posts"] == []
