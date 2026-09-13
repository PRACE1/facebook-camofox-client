"""Social accounts store tests — temp SQLite, synthetic cookies only."""
import pytest

from facebook_camofox_client.domain_accounts.store import SocialAccountStore


@pytest.fixture
def store(tmp_path):
    return SocialAccountStore(tmp_path / "accounts.db")


def test_roundtrip(store):
    cookies = [{"name": "c_user", "value": "123", "domain": ".facebook.com"}]
    store.save("acc-1", cookies, label="Galway 1")
    assert store.load_cookies("acc-1") == cookies
    assert store.load_cookies("missing") is None


def test_metadata_never_leaks_cookies(store):
    store.save("acc-1", [{"name": "xs", "value": "SECRET"}])
    meta = store.metadata()
    assert meta[0]["account_id"] == "acc-1"
    assert "SECRET" not in str(meta)


def test_validation(store):
    with pytest.raises(ValueError):
        store.save("", [{"name": "a", "value": "b"}])
    with pytest.raises(ValueError):
        store.save("acc-1", [])


def test_delete(store):
    store.save("acc-1", [{"name": "a", "value": "b"}])
    assert store.delete("acc-1") is True
    assert store.delete("acc-1") is False
    assert store.load_cookies("acc-1") is None


def test_api_accounts_roundtrip(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from facebook_camofox_client.api import app as app_module

    monkeypatch.setenv("SOCIAL_ACCOUNTS_DB", str(tmp_path / "api.db"))
    c = TestClient(app_module.app)
    r = c.post("/api/accounts", json={"account_id": "a1", "label": "t",
                                      "cookies": [{"name": "c", "value": "v"}]})
    assert r.status_code == 201
    listed = c.get("/api/accounts").json()
    assert [m["account_id"] for m in listed] == ["a1"]
    assert "v" not in str(listed)
    assert c.delete("/api/accounts/a1").status_code == 200
    assert c.delete("/api/accounts/a1").status_code == 404
