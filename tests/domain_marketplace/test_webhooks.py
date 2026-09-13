"""Webhook builder + dispatcher tests — no network (monkeypatched httpx)."""
import pytest

from facebook_camofox_client.domain_marketplace import webhooks
from facebook_camofox_client.domain_marketplace.webhooks import (
    alert_raised_event,
    created_event,
    dispatch,
    health_checked_event,
    post_new_event,
    superseded_event,
)


def test_created_shape():
    p = created_event(listing_id="1", offer_id="o", status="UNDER_REVIEW",
                      generation=0, root_listing_id="1", parent_listing_id=None,
                      title="T", location_query="Galway, Ireland", price=50,
                      screenshot_url="s.png")
    assert p["event"] == "listing.created"
    assert p["data"]["listingId"] == "1" and p["data"]["price"] == 50
    assert "timestamp" in p


def test_all_four_events_named():
    assert health_checked_event(listing_id="1", status="ACTIVE")["event"] == "listing.health_checked"
    assert superseded_event(old_listing_id="1", new_listing_id="2", offer_id="o",
                            reason="DUPLICATE_TAKEDOWN", generation=1,
                            root_listing_id="1", new_title="T")["event"] == "listing.superseded"
    assert alert_raised_event(listing_id="1", root_listing_id="1", offer_id="o",
                              alert_type="RETRY_EXHAUSTED",
                              message="m")["event"] == "listing.alert_raised"


@pytest.mark.asyncio
async def test_dispatch_no_endpoint_is_noop():
    assert await dispatch({"event": "x"}, url=None) is None


@pytest.mark.asyncio
async def test_dispatch_failure_never_raises(monkeypatch):
    class Boom:
        def __init__(self, *a, **k): pass

        async def __aenter__(self): raise RuntimeError("net down")

        async def __aexit__(self, *a): pass

    monkeypatch.setattr(webhooks.httpx, "AsyncClient", Boom)
    assert await dispatch({"event": "x"}, url="http://127.0.0.1:9/hook") is False


@pytest.mark.asyncio
async def test_dispatch_success(monkeypatch):
    class Resp:
        status_code = 200

    class Client:
        def __init__(self, *a, **k): pass

        async def __aenter__(self): return self

        async def __aexit__(self, *a): pass

        async def post(self, url, json=None):
            Client.last_url = url
            return Resp()

    Client.last_url = ""
    monkeypatch.setattr(webhooks.httpx, "AsyncClient", Client)
    assert await dispatch({"event": "x"}, url="http://crm/hook") is True
    assert Client.last_url == "http://crm/hook"


@pytest.mark.asyncio
async def test_dispatch_env_fallback_prefers_posts_url(monkeypatch):
    seen = []

    class Resp:
        status_code = 200

    class Client:
        def __init__(self, *a, **k): pass

        async def __aenter__(self): return self

        async def __aexit__(self, *a): pass

        async def post(self, url, json=None):
            seen.append(url)
            return Resp()

    monkeypatch.setattr(webhooks.httpx, "AsyncClient", Client)
    monkeypatch.setenv("POSTS_WEBHOOK_URL", "http://crm/posts")
    monkeypatch.setenv("MARKETPLACE_WEBHOOK_URL", "http://crm/mkt")
    assert await dispatch({"event": "posts.new"},
                          env_vars=("POSTS_WEBHOOK_URL", "MARKETPLACE_WEBHOOK_URL")) is True
    assert seen == ["http://crm/posts"]
    monkeypatch.delenv("POSTS_WEBHOOK_URL")
    assert await dispatch({"event": "posts.new"},
                          env_vars=("POSTS_WEBHOOK_URL", "MARKETPLACE_WEBHOOK_URL")) is True
    assert seen[-1] == "http://crm/mkt"


def test_post_new_shape_and_truncation():
    p = post_new_event(action_id="a", group_id="g", record_id="r", post_id="p",
                       content="x" * 600, url="u", author="n",
                       occurred_at="2026-09-12T00:00:00+00:00")
    assert p["event"] == "posts.new"
    assert p["data"]["groupId"] == "g" and p["data"]["postId"] == "p"
    assert len(p["data"]["content"]) == 500
