"""
Limits kept in the database (so a server restart doesn't reset them),
the per-device limits on requests that send email, removing sign-ups
never verified, and the email setup checks run at startup.
"""

import datetime as dt
import importlib

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from tellspend.database.config import settings
from tellspend.database.models import Counterparty, RateEvent, User
from tellspend.services import rate_limit, startup_checks
from tellspend.services.accounts_cleanup import remove_stale_unverified


# ---------- a restart forgets nothing ----------


def test_a_locked_login_stays_locked_after_a_restart(db):
    for _ in range(settings.login_max_failures):
        rate_limit.record_login_failure(db, "a@example.com", "1.2.3.4")

    # A restart: the module is loaded fresh; nothing was kept in memory.
    fresh = importlib.reload(rate_limit)

    with pytest.raises(HTTPException) as locked:
        fresh.check_login_allowed(db, "a@example.com", "1.2.3.4")
    assert locked.value.status_code == 429


def test_the_assistants_daily_count_survives_a_restart(db, monkeypatch):
    monkeypatch.setattr(settings, "assistant_requests_per_day", 2)
    rate_limit.check_assistant_limit(db, 7, now=1000.0)
    rate_limit.check_assistant_limit(db, 7, now=1100.0)

    fresh = importlib.reload(rate_limit)

    with pytest.raises(HTTPException) as refused:
        fresh.check_assistant_limit(db, 7, now=1200.0)
    assert refused.value.status_code == 429


def test_rows_older_than_a_day_are_cleared(db):
    rate_limit.record_login_failure(db, "old@example.com", "1.1.1.1", now=1_000_000.0)
    rate_limit.record_login_failure(db, "new@example.com", "1.1.1.1", now=1_000_000.0 + 2 * 24 * 3600)

    keys = set(db.scalars(select(RateEvent.key)))
    assert not any("old@example.com" in key for key in keys)
    assert any("new@example.com" in key for key in keys)


# ---------- requests that send email, per device ----------


def signup(client, email, password="secret123"):
    return client.post("/users", json={"email": email, "name": "x", "password": password})


def test_one_device_can_sign_up_only_so_often(client, monkeypatch):
    monkeypatch.setattr(settings, "signups_per_hour", 3)

    codes = [signup(client, f"user{i}@example.com").status_code for i in range(4)]

    assert codes == [201, 201, 201, 429]


def test_one_device_can_ask_for_reset_links_only_so_often(client, monkeypatch):
    monkeypatch.setattr(settings, "reset_requests_per_hour", 2)

    codes = [client.post("/auth/forgot-password", json={"email": f"n{i}@example.com"}).status_code for i in range(3)]

    # Unknown emails (404) still count: that's what stops testing emails in bulk.
    assert codes == [404, 404, 429]


def test_one_device_can_ask_for_new_codes_only_so_often(client, monkeypatch):
    monkeypatch.setattr(settings, "code_requests_per_hour", 2)

    codes = [client.post("/auth/resend-verification", json={"email": "z@example.com"}).status_code for _ in range(3)]

    assert codes == [202, 202, 429]


def test_another_device_isnt_held_up(client, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "reset_requests_per_hour", 1)
    first = {"X-Forwarded-For": "5.5.5.5"}

    client.post("/auth/forgot-password", json={"email": "a@example.com"}, headers=first)
    blocked = client.post("/auth/forgot-password", json={"email": "a@example.com"}, headers=first)
    other = client.post("/auth/forgot-password", json={"email": "a@example.com"}, headers={"X-Forwarded-For": "6.6.6.6"})

    assert blocked.status_code == 429 and other.status_code == 404


# ---------- sign-ups never verified ----------


def test_old_unverified_sign_ups_are_removed_and_others_kept(client, db):
    signup(client, "stale@example.com")
    signup(client, "fresh@example.com")
    signup(client, "kept@example.com")
    db.execute(
        User.__table__.update().where(User.email == "kept@example.com").values(email_verified_at=func.now())
    )
    db.commit()

    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=settings.unverified_account_hours + 1)
    db.execute(User.__table__.update().where(User.email == "fresh@example.com").values(created_at=later))
    db.commit()

    removed = remove_stale_unverified(db, now=later)

    emails = set(db.scalars(select(User.email)))
    assert removed == 1
    assert "stale@example.com" not in emails
    assert {"fresh@example.com", "kept@example.com"} <= emails


def test_an_unverified_account_that_holds_data_is_never_removed(client, db):
    # Accounts made before email verification existed are "unverified" too.
    signup(client, "legacy@example.com")
    user = db.scalar(select(User).where(User.email == "legacy@example.com"))
    db.add(Counterparty(owner_user_id=user.id, name="Parth", counterparty_type="PERSON"))
    db.commit()

    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=settings.unverified_account_hours + 1)
    removed = remove_stale_unverified(db, now=later)

    assert removed == 0
    assert db.scalar(select(User).where(User.email == "legacy@example.com")) is not None


# ---------- email setup checks at startup ----------


@pytest.mark.parametrize(
    "backend, key, sender, says",
    [
        ("brevo", "xsmtpsib-abc", "TellSpend <me@mydomain.com>", "SMTP key"),
        ("brevo", "", "TellSpend <me@mydomain.com>", "BREVO_API_KEY is empty"),
        ("smtp", None, "TellSpend <you@gmail.com>", "example address"),
    ],
)
def test_a_broken_email_setup_is_named(monkeypatch, backend, key, sender, says):
    monkeypatch.setattr(settings, "email_backend", backend)
    monkeypatch.setattr(settings, "brevo_api_key", key)
    monkeypatch.setattr(settings, "email_from", sender)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_username", "me")
    monkeypatch.setattr(settings, "smtp_password", "pw")

    assert any(says in problem for problem in startup_checks.email_problems())


def test_a_good_email_setup_has_no_problems(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "brevo")
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-abc")
    monkeypatch.setattr(settings, "email_from", "TellSpend <noreply@tellspend.in>")

    assert startup_checks.email_problems() == []
