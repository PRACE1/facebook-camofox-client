"""Marketplace status classifier + action tests — fakes only."""
import pytest

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_marketplace.status import (
    MarketplaceStatusAction,
    classify_status,
)


def test_classify_duplicate_beats_active():
    assert classify_status("https://www.facebook.com/marketplace/item/1/",
                           "Rubbish Removal in Galway",
                           "This might be a duplicate listing") == "under-review-duplicate"


def test_classify_login_wall():
    assert classify_status("https://www.facebook.com/login/", "", "") == "login-wall"


def test_classify_unknown_when_empty():
    assert classify_status("https://www.facebook.com/marketplace/item/1/", "", "") == "unknown"


class FakeLocator:
    def __init__(self, text="Rubbish Removal in Galway"): self._text = text
    async def inner_text(self, timeout=None): return self._text


class FakePage:
    def __init__(self, url, title, body):
        self.url, self._title, self._body = url, title, body

    async def goto(self, *a, **k): pass
    async def wait_for_timeout(self, ms): pass
    async def title(self): return self._title
    def locator(self, sel): return FakeLocator(self._body)


class FakeSession:
    def __init__(self, page): self._page = page
    async def new_page(self): return self._page


class FakeManager:
    def __init__(self, page): self._page = page
    async def acquire(self, account_id, **k): return FakeSession(self._page)
    async def release(self, session): pass


@pytest.mark.asyncio
async def test_status_action_emits_checked():
    page = FakePage("https://www.facebook.com/marketplace/item/38629807913299080/",
                    "Rubbish Removal in Galway", "Rubbish Removal in Galway BWP50")
    emitter = InMemoryEventEmitter()
    action = MarketplaceStatusAction(FakeManager(page), emitter)
    env = ActionEnvelope(action_id="s1", action_type="marketplace.status",
                         account_id="acc", input={"listing_id": "38629807913299080"},
                         idempotency_key="k1")
    out = await action.execute(env)
    assert out.status == "active"
    assert out.listing_id == "38629807913299080"
    assert any(e.event_type == "marketplace.status_checked" for e in emitter.events)
