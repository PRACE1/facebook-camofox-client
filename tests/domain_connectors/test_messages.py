"""Messages client tests — fake HTTP layer, no credentials, no network."""
import pytest

from facebook_camofox_client.domain_connectors import messages as msg_mod
from facebook_camofox_client.domain_connectors.messages import MessagesClient


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def _client(handler):
    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url, params=None, headers=None):
            return handler("GET", url, params, None)

    return Client


@pytest.mark.asyncio
async def test_list_messages(monkeypatch):
    def handler(method, url, params, body):
        assert url.endswith("/messages")
        return FakeResp({"data": {"messages": [{"id": "m-1", "subject": "hi"}]}, "totalCount": 1})

    monkeypatch.setattr(msg_mod.httpx, "AsyncClient", _client(handler))
    rows, total = await MessagesClient("https://x/rest", "k").list_messages(limit=5)
    assert total == 1 and rows[0]["id"] == "m-1"


@pytest.mark.asyncio
async def test_get_message_404(monkeypatch):
    def handler(method, url, params, body):
        return FakeResp({}, status=404)

    monkeypatch.setattr(msg_mod.httpx, "AsyncClient", _client(handler))
    assert await MessagesClient("https://x/rest", "k").get_message("missing") is None


@pytest.mark.asyncio
async def test_create_blocked():
    with pytest.raises(ValueError, match="writes disabled"):
        await MessagesClient("https://x/rest", "k").create_message({"subject": "x"})
