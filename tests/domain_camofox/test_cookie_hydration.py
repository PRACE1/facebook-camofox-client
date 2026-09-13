"""cookie_hydration unit tests — SYNTHETIC Chrome-format samples only.

These validate pure mapping logic (sameSite/expires/defaults), NOT any
real-world login. No live session, no real cookies."""
import pytest

from facebook_camofox_client.domain_camofox.cookie_hydration import (
    AuthExpiredError,
    extract_cookie_list,
    is_logged_in,
    normalize_chrome_cookie,
    normalize_chrome_cookies,
)


def test_samesite_mapping():
    assert normalize_chrome_cookie(
        {"name": "a", "value": "1", "sameSite": "no_restriction", "secure": True}
    )["sameSite"] == "None"
    assert normalize_chrome_cookie(
        {"name": "a", "value": "1", "sameSite": "unspecified"}
    )["sameSite"] == "Lax"


def test_samesite_none_without_secure_downgrades():
    c = normalize_chrome_cookie({"name": "a", "value": "1", "sameSite": "None"})
    assert c["sameSite"] == "Lax"


def test_expiration_float_to_int_and_session_skip():
    c = normalize_chrome_cookie(
        {"name": "a", "value": "1", "expirationDate": 1893456000.5})
    assert c["expires"] == 1893456000 and isinstance(c["expires"], int)
    c2 = normalize_chrome_cookie(
        {"name": "a", "value": "1", "session": True, "expirationDate": 1893456000.0})
    assert "expires" not in c2


def test_defaults_and_bad_rows_skipped():
    out = normalize_chrome_cookies([
        {"name": "c_user", "value": "123"},
        {"name": "", "value": "x"},
        {"nope": True},
    ])
    assert len(out) == 1
    assert out[0]["domain"] == ".facebook.com" and out[0]["path"] == "/"


def test_extract_accepts_list_or_storage_state():
    assert extract_cookie_list([{"name": "a"}]) == [{"name": "a"}]
    assert extract_cookie_list({"cookies": [{"name": "a"}]}) == [{"name": "a"}]
    with pytest.raises(ValueError):
        extract_cookie_list({"origins": []})


def test_is_logged_in():
    assert is_logged_in("https://www.facebook.com/", "Facebook") is True
    assert is_logged_in("https://www.facebook.com/login/", "Log in") is False
    assert AuthExpiredError is not None
