"""Group post action tests — fakes only, no browser."""
import pytest

from facebook_camofox_client.domain_actions.envelope import ActionEnvelope
from facebook_camofox_client.domain_events.emitter import InMemoryEventEmitter
from facebook_camofox_client.domain_groups import post_driver as drv
from facebook_camofox_client.domain_groups.post import GroupPostAction


class FakeManager:
    async def acquire(self, account_id, **k):
        class FakePage:
            url = "https://www.facebook.com/groups/305056891435827"

            async def title(self): return "Test Group"
            async def goto(self, *a, **k): pass
            async def wait_for_timeout(self, ms): pass
        class FakeSession:
            async def new_page(self): return FakePage()
        return FakeSession()

    async def release(self, session): pass


def make_envelope(**over):
    payload = {"group_id": "305056891435827", "message": "hello",
               "image_paths": [], "dry_run": True}
    payload.update(over)
    return ActionEnvelope(action_id="g1", action_type="groups.post",
                          account_id="acc", input=payload, idempotency_key="k1")


@pytest.mark.asyncio
async def test_dry_run_emits_completed(monkeypatch):
    async def fake_fill(page, message, images=None): return True
    monkeypatch.setattr(drv, "fill_composer", fake_fill)
    emitter = InMemoryEventEmitter()
    out = await GroupPostAction(FakeManager(), emitter).execute(make_envelope())
    assert out["posted"] is False
    assert any(e.event_type == "groups.post_completed" for e in emitter.events)


@pytest.mark.asyncio
async def test_composer_miss_emits_failed(monkeypatch):
    async def fake_fill(page, message, images=None): return False
    monkeypatch.setattr(drv, "fill_composer", fake_fill)
    emitter = InMemoryEventEmitter()
    out = await GroupPostAction(FakeManager(), emitter).execute(make_envelope())
    assert out["posted"] is False
    failed = [e for e in emitter.events if e.event_type == "groups.post_failed"]
    assert failed and failed[0].payload["reason"] == "composer_not_found"
