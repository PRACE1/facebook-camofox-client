"""Marketplace create action tests — fakes only, no browser."""

import pytest

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_marketplace import form_driver as driver
from facebook_camofox_client.domain_marketplace.create import MarketplaceCreateAction


class FakeLocator:
    def __init__(self, page=None, count=1, text=""):
        self._page, self._count, self._text = page, count, text

    def __getattr__(self, name):
        if name in ("first", "last"):
            return self
        raise AttributeError(name)

    async def count(self): return self._count
    async def is_visible(self): return True
    async def scroll_into_view_if_needed(self): pass
    async def click(self, timeout=None, force=None): pass
    async def fill(self, *a, **k): pass
    async def type(self, *a, **k): pass
    async def wait_for(self, state=None, timeout=None): pass
    async def get_attribute(self, name): return "false" if name == "aria-disabled" else None
    async def is_disabled(self): return False
    async def inner_text(self, timeout=None): return self._text
    async def input_value(self, timeout=None): return self._text
    async def evaluate(self, js): return ""
    def locator(self, *a, **k): return FakeLocator(self._page, count=0)
    def get_by_role(self, *a, **k): return FakeLocator(self._page, count=0)
    def nth(self, i): return self


class FakeKeyboard:
    async def press(self, *a): pass
    async def type(self, *a, **k): pass


class FakePage:
    url = "https://www.facebook.com/marketplace/create/item"

    def __init__(self):
        self.keyboard = FakeKeyboard()
        self.clicked = []

    def locator(self, sel):
        if "file" in sel:
            return FakeLocator(self, count=1)
        if "combobox" in sel and "Location" in sel:
            return FakeLocator(self, count=1)
        if "textarea" in sel:
            return FakeLocator(self, count=1)
        if 'input[type="text"]' in sel:
            return FakeLocator(self, count=2)
        return FakeLocator(self, count=0)

    def get_by_role(self, role, name=None):
        if role == "button":
            return FakeLocator(self, count=1)
        return FakeLocator(self, count=0)

    async def goto(self, *a, **k): pass
    async def wait_for_timeout(self, ms): pass
    async def wait_for_url(self, *a, **k): pass
    async def evaluate(self, js): return []
    async def screenshot(self, path=None, full_page=None): pass
    async def content(self): return "<html></html>"
    async def title(self): return "Item for sale"


class FakeSession:
    def __init__(self, page): self._page = page
    async def new_page(self): return self._page


class FakeManager:
    def __init__(self, page): self._page = page
    async def acquire(self, account_id, **k): return FakeSession(self._page)
    async def release(self, session): pass


def make_envelope(**input_over):
    payload = {"title": "T", "price": "50", "category": "Household",
               "description": "d", "location": "Galway, Ireland",
               "image_paths": [], "dry_run": True}
    payload.update(input_over)
    return ActionEnvelope(action_id="a1", action_type="marketplace.create",
                          account_id="acc", input=payload, idempotency_key="k1")


@pytest.mark.asyncio
async def test_dry_run_fills_and_emits_completed(monkeypatch):
    async def fake_select(page, name, value): return True
    async def fake_clear(loc, page, value, delay=20): pass
    monkeypatch.setattr(driver, "select_combobox", fake_select)
    monkeypatch.setattr(driver, "clear_and_type", fake_clear)
    emitter = InMemoryEventEmitter()
    action = MarketplaceCreateAction(FakeManager(FakePage()), emitter)
    out = await action.execute(make_envelope())
    assert out.published is False
    assert any(e.event_type == "marketplace.create_completed" for e in emitter.events)


@pytest.mark.asyncio
async def test_auth_required_short_circuits(monkeypatch):
    async def fake_select(page, name, value): return True  # pragma: no cover
    monkeypatch.setattr(driver, "select_combobox", fake_select)
    page = FakePage()
    page.url = "https://www.facebook.com/login/"
    emitter = InMemoryEventEmitter()
    action = MarketplaceCreateAction(FakeManager(page), emitter)
    out = await action.execute(make_envelope())
    assert out.published is False
    assert any(e.event_type == "marketplace.create_failed" for e in emitter.events)


@pytest.mark.asyncio
async def test_category_miss_emits_failed(monkeypatch):
    async def fake_select(page, name, value): return False
    monkeypatch.setattr(driver, "select_combobox", fake_select)
    emitter = InMemoryEventEmitter()
    action = MarketplaceCreateAction(FakeManager(FakePage()), emitter)
    out = await action.execute(make_envelope())
    assert out.published is False
    failed = [e for e in emitter.events if e.event_type == "marketplace.create_failed"]
    assert failed and failed[0].payload["reason"] == "category_not_opened"


@pytest.mark.asyncio
async def test_unknown_category_fails_before_browser(monkeypatch):
    called = []

    class NoSessionManager:
        async def acquire(self, account_id, **k):
            called.append(account_id)
            raise AssertionError("browser must not launch for unknown category")

        async def release(self, session): pass

    emitter = InMemoryEventEmitter()
    out = await MarketplaceCreateAction(NoSessionManager(), emitter).execute(
        make_envelope(category="Starships"))
    assert out.published is False and out.success is False
    assert called == []
    failed = [e for e in emitter.events if e.event_type == "marketplace.create_failed"]
    assert failed and failed[0].payload["reason"] == "unknown_category"


def test_resolve_category():
    from facebook_camofox_client.domain_marketplace.categories import resolve_category
    assert resolve_category("household") == "Household"
    assert resolve_category("Household") == "Household"
    assert resolve_category("SERVICES") == "Services"
    assert resolve_category("Starships") is None
    assert resolve_category("") is None
