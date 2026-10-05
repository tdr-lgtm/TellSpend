"""
Tests for email verification (a 6-digit code; no sign-in before it) and
password reset (a single-use link). Emails are captured instead of sent.
"""

import datetime as dt
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from sqlalchemy import update

from tellspend.api.auth import ALGORITHM
from tellspend.database.config import settings
from tellspend.database.models import AuthToken
from tellspend.services import account_emails


@pytest.fixture
def outbox(monkeypatch):
    """Every email "sent", as (to, subject, body)."""
    sent = []

    def capture(to, subject, body):
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr(account_emails, "send_email", capture)
    return sent


@pytest.fixture
def no_wait(monkeypatch):
    """Let a new email go out straight after the last one."""
    monkeypatch.setattr(settings, "email_resend_seconds", 0)


def code_in(email) -> str:
    """The 6-digit code in an email's body."""
    [code] = [word for word in email[2].split() if len(word) == 6 and word.isdigit()]
    return code


def link_token(email) -> str:
    """The token from the link in an email's body."""
    [url] = [word for word in email[2].split() if word.startswith("http")]
    return parse_qs(urlparse(url).query)["token"][0]


def signup(client, email="xyz@example.com", password="secret123"):
    return client.post("/users", json={"email": email, "name": "xyz", "password": password})


def login(client, email="xyz@example.com", password="secret123"):
    return client.post("/auth/token", data={"username": email, "password": password})


def verify(client, code, email="xyz@example.com"):
    return client.post("/auth/verify-email", json={"email": email, "code": code})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def other_code(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


# ---------- verifying the email with a code ----------


def test_signing_up_emails_a_code_and_the_code_signs_you_in(client, outbox):
    body = signup(client).json()
    assert body["email_verified"] is False

    [email] = outbox
    assert email[0] == "xyz@example.com"
    code = code_in(email)
    assert code in email[1]

    response = verify(client, code, email="  XYZ@example.com ")

    assert response.status_code == 200
    me = client.get("/auth/me", headers=bearer(response.json()["access_token"])).json()
    assert me["email_verified"] is True


def test_no_sign_in_before_the_email_is_verified(client, outbox):
    signup(client)

    response = login(client)

    assert response.status_code == 403
    assert "enter the code" in response.json()["detail"]


def test_signing_in_unverified_sends_a_fresh_code(client, outbox, no_wait):
    signup(client)

    login(client)

    first, second = outbox
    assert verify(client, code_in(first)).status_code == 400
    assert verify(client, code_in(second)).status_code == 200


def test_a_wrong_password_never_says_whether_the_email_is_verified(client, outbox):
    signup(client)

    response = login(client, password="not-the-password")

    assert response.status_code == 401
    assert len(outbox) == 1


def test_an_old_login_of_an_unverified_account_is_refused(client, outbox):
    user_id = signup(client).json()["id"]
    token = jwt.encode(
        {"sub": str(user_id), "iat": int(dt.datetime.now(dt.timezone.utc).timestamp()),
         "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30)},
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_a_code_works_once(client, outbox):
    signup(client)
    code = code_in(outbox[0])

    verify(client, code)
    again = verify(client, code)

    assert again.status_code == 400
    assert "already verified" in again.json()["detail"]


def test_a_wrong_code_is_refused_and_too_many_retire_the_code(client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "verify_code_attempts", 3)
    signup(client)
    code = code_in(outbox[0])

    first = verify(client, other_code(code))
    assert first.status_code == 400
    assert "isn't right" in first.json()["detail"]
    verify(client, other_code(code))
    third = verify(client, other_code(code))
    assert "too many tries" in third.json()["detail"]

    # After that even the right code doesn't work: a new one is needed.
    assert verify(client, code).status_code == 400


def test_an_expired_code_is_refused(client, outbox, db):
    signup(client)
    db.execute(update(AuthToken).values(expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)))

    response = verify(client, code_in(outbox[0]))

    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_an_unknown_email_gets_the_same_answer_as_an_expired_code(client, outbox):
    response = verify(client, "123456", email="nobody@example.com")

    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


@pytest.mark.parametrize("code", ["12345", "1234567", "12a456", ""])
def test_a_code_must_be_six_digits(client, outbox, code):
    assert verify(client, code).status_code == 422


def test_spaces_in_a_typed_code_dont_matter(client, outbox):
    signup(client)
    code = code_in(outbox[0])

    assert verify(client, f"{code[:3]} {code[3:]}").status_code == 200


# ---------- asking for a new code ----------


def resend(client, email="xyz@example.com"):
    return client.post("/auth/resend-verification", json={"email": email})


def test_a_new_code_retires_the_old_one(client, outbox, no_wait):
    signup(client)

    response = resend(client)

    assert response.status_code == 202
    first, second = outbox
    assert verify(client, code_in(first)).status_code == 400
    assert verify(client, code_in(second)).status_code == 200


def test_resend_answers_the_same_for_any_email_and_only_emails_unverified_accounts(
    client, outbox, no_wait
):
    signup(client)
    signup(client, email="done@example.com")
    verify(client, code_in(outbox[1]), email="done@example.com")
    outbox.clear()

    answers = [resend(client, email).json() for email in
               ["xyz@example.com", "done@example.com", "nobody@example.com"]]

    assert answers[0] == answers[1] == answers[2]
    assert [email[0] for email in outbox] == ["xyz@example.com"]


def test_resending_moments_later_sends_nothing_new(client, outbox):
    signup(client)

    resend(client)

    assert len(outbox) == 1


# ---------- resetting the password ----------


def forgot(client, email="xyz@example.com"):
    return client.post("/auth/forgot-password", json={"email": email})


def test_forgot_password_answers_the_same_for_any_email(client, outbox):
    signup(client)
    outbox.clear()

    known = forgot(client, "  XYZ@example.com ")
    unknown = forgot(client, "nobody@example.com")

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    [email] = outbox
    assert email[0] == "xyz@example.com"
    assert "/reset-password?token=" in email[2]


def test_a_reset_changes_the_password_verifies_the_email_and_signs_out_old_logins(client, outbox):
    user_id = signup(client).json()["id"]
    # A login from before the reset (issued a while ago).
    old_login = jwt.encode(
        {
            "sub": str(user_id),
            "iat": int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).timestamp()),
            "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30),
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    outbox.clear()

    forgot(client)
    response = client.post(
        "/auth/reset-password", json={"token": link_token(outbox[0]), "password": "brand-new-9"}
    )

    assert response.status_code == 200
    assert login(client).status_code == 401
    # Resetting through the emailed link proves the address, so sign-in works.
    new_login = login(client, password="brand-new-9")
    assert new_login.status_code == 200
    assert client.get("/auth/me", headers=bearer(old_login)).status_code == 401
    me = client.get("/auth/me", headers=bearer(new_login.json()["access_token"])).json()
    assert me["email_verified"] is True


def test_a_reset_link_works_once(client, outbox):
    signup(client)
    forgot(client)
    reset_link = link_token(outbox[-1])

    assert client.post(
        "/auth/reset-password", json={"token": reset_link, "password": "brand-new-9"}
    ).status_code == 200
    assert client.post(
        "/auth/reset-password", json={"token": reset_link, "password": "another-one-9"}
    ).status_code == 400


def test_a_new_password_follows_the_signup_rules(client, outbox):
    signup(client)
    forgot(client)

    response = client.post(
        "/auth/reset-password", json={"token": link_token(outbox[-1]), "password": "short"}
    )

    assert response.status_code == 422


def test_asking_again_moments_later_sends_nothing_new(client, outbox):
    signup(client)
    outbox.clear()

    forgot(client)
    forgot(client)

    assert len(outbox) == 1
