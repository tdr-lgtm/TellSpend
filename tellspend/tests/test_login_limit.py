"""
Wrong-password limits on login: after too many wrong passwords for an
email, logins for it are refused (even with the right password, so
guessing on gives no hint) until the window passes.
"""

import pytest

from conftest import mark_verified
from tellspend.database.config import settings
from tellspend.services import rate_limit

EMAIL = "xyz@example.com"


def signup(client, email=EMAIL):
    client.post("/users", json={"email": email, "name": "xyz", "password": "secret123"})


def login(client, password="secret123", email=EMAIL, headers=None):
    return client.post("/auth/token", data={"username": email, "password": password}, headers=headers or {})


@pytest.fixture
def user(client, db):
    signup(client)
    mark_verified(db, EMAIL)


def test_five_wrong_passwords_lock_the_account_even_for_the_right_one(client, user):
    for _ in range(settings.login_max_failures):
        assert login(client, "wrong-password").status_code == 401

    locked = login(client)

    assert locked.status_code == 429
    assert "Too many wrong passwords" in locked.json()["detail"]
    assert 0 < int(locked.headers["Retry-After"]) <= settings.login_window_minutes * 60


def test_fewer_wrong_passwords_still_let_the_right_one_in_and_are_then_forgiven(client, user):
    for _ in range(settings.login_max_failures - 1):
        login(client, "wrong-password")

    assert login(client).status_code == 200
    # Forgiven: another full set of tries before a lock.
    for _ in range(settings.login_max_failures - 1):
        assert login(client, "wrong-password").status_code == 401
    assert login(client).status_code == 200


def test_unknown_emails_are_limited_the_same_way(client):
    # Otherwise the limit would show which emails have accounts.
    for _ in range(settings.login_max_failures):
        assert login(client, email="nobody@example.com").status_code == 401

    assert login(client, email="nobody@example.com").status_code == 429


def test_one_locked_account_doesnt_lock_another(client, user, db):
    signup(client, "other@example.com")
    mark_verified(db, "other@example.com")
    for _ in range(settings.login_max_failures):
        login(client, "wrong-password")

    assert login(client, email="other@example.com").status_code == 200


def test_the_lock_lifts_when_the_window_passes():
    now = 1_000_000.0
    for i in range(settings.login_max_failures):
        rate_limit.record_login_failure(EMAIL, "1.2.3.4", now + i)

    with pytest.raises(Exception) as locked:
        rate_limit.check_login_allowed(EMAIL, "1.2.3.4", now + 10)
    assert locked.value.status_code == 429

    # The oldest failure ages out of the window: one more try is allowed.
    rate_limit.check_login_allowed(EMAIL, "1.2.3.4", now + settings.login_window_minutes * 60 + 1)


def test_guessing_from_many_addresses_is_capped_per_account():
    now = 1_000_000.0
    for i in range(settings.login_max_failures_per_account):
        rate_limit.record_login_failure(EMAIL, f"10.0.0.{i}", now)

    with pytest.raises(Exception) as locked:
        rate_limit.check_login_allowed(EMAIL, "10.0.1.1", now + 1)
    assert locked.value.status_code == 429


def test_behind_a_trusted_proxy_each_client_is_counted_separately(client, user, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    attacker = {"X-Forwarded-For": "6.6.6.6, 10.0.0.1"}
    for _ in range(settings.login_max_failures):
        login(client, "wrong-password", headers=attacker)

    assert login(client, headers=attacker).status_code == 429
    assert login(client, headers={"X-Forwarded-For": "7.7.7.7"}).status_code == 200
