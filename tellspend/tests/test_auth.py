from datetime import datetime, timedelta, timezone
import jwt
from tellspend.database.config import settings
from conftest import mark_verified

def signup(client, email="xyz@example.com", password="secret123", **extra):
    # Create an account and return the response
    return client.post(
        "/users",
        json={"email": email, "name": "xyz", "password": password, **extra},
    )

def login(client, email="xyz@example.com", password="secret123"):
    # Log in and return the response
    return client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )

def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

# sign up
def test_signup_creates_user_without_exposing_password(client):
    response = signup(client, email="  Xyz@Example.COM ", default_currency="inr")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "xyz@example.com"
    assert body["name"] == "xyz"
    assert body["default_currency"] == "INR"
    assert "password" not in body
    assert "password_hash" not in body

def test_signup_defaults_currency_to_inr(client):
    assert signup(client).json()["default_currency"] == "INR"

def test_signup_rejects_duplicate_email_in_any_case(client):
    signup(client, email="xyz@example.com")

    response = signup(client, email="XYZ@example.com")

    assert response.status_code == 409

def test_signup_rejects_bad_input(client):
    assert signup(client, email="not-an-email").status_code == 422
    assert signup(client, password="short").status_code == 422
    assert signup(client, default_currency="12").status_code == 422
    assert client.post(
        "/users",
        json={"email": "a@b.com", "name": "   ", "password": "secret123"},
    ).status_code == 422

# log in
def test_login_returns_token_for_correct_password(client, db):
    signup(client)
    mark_verified(db, "xyz@example.com")

    response = login(client, email="  XYZ@example.com")

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_gives_same_error_for_wrong_password_and_unknown_email(client):
    signup(client)

    wrong_password = login(client, password="wrong-password")
    unknown_email = login(client, email="nobody@example.com")

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()

# /auth/me
def test_me_returns_signed_in_user(client, db):
    signup(client)
    mark_verified(db, "xyz@example.com")
    token = login(client).json()["access_token"]

    response = client.get("/auth/me", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["email"] == "xyz@example.com"

def test_me_rejects_missing_or_garbage_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=auth_header("garbage")).status_code == 401

def test_me_rejects_expired_token(client):
    user_id = signup(client).json()["id"]
    expired = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm="HS256",
    )

    assert client.get("/auth/me", headers=auth_header(expired)).status_code == 401


def test_me_rejects_token_signed_with_another_key(client):
    user_id = signup(client).json()["id"]
    forged = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "some-other-key-that-is-at-least-32-characters-long",
        algorithm="HS256",
    )

    assert client.get("/auth/me", headers=auth_header(forged)).status_code == 401

def test_me_rejects_token_for_user_that_does_not_exist(client):
    token = jwt.encode(
        {"sub": "999999", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm="HS256",
    )

    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401