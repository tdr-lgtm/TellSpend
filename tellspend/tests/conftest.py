from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, update
from sqlalchemy.orm import Session

from tellspend.database.config import settings
from tellspend.database.connection import get_db
from tellspend.database.models import Base, User
from tellspend.main import app


TEST_DATABASE_URL = settings.database_url + "_test"

test_engine = create_engine(TEST_DATABASE_URL)

@pytest.fixture(autouse=True)
def never_send_real_email(monkeypatch) -> None:
    # Tests print emails instead of sending them, whatever .env says.
    monkeypatch.setattr(settings, "email_backend", "console")


@pytest.fixture(scope="session", autouse=True)
def create_tables() -> Generator[None, None, None]:
    # Build every table fresh at the start of the test run.
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield

@pytest.fixture
def db() -> Generator[Session, None, None]:
    """
    A session inside a transaction that is always rolled back.
    Commits made by the routes only close a savepoint inside it.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    # An API client whose routes all use the test session.
    app.dependency_overrides[get_db] = lambda: db

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def mark_verified(db: Session, email: str) -> None:
    """What entering the emailed code does, for tests that just need a user."""
    db.execute(
        update(User).where(User.email == email).values(email_verified_at=func.now())
    )
    # Committed (inside the test's transaction) like real verification, so
    # a route's rollback later can't undo it.
    db.commit()


@pytest.fixture
def make_user(client: TestClient, db: Session):
    """
    Returns a function that signs up, verifies and logs in a user and
    gives back their Authorization header, e.g. headers = make_user("a@x.com").
    """
    def _make_user(email: str = "xyz@example.com", default_currency: str = "INR") -> dict:
        client.post(
            "/users",
            json={
                "email": email,
                "name": email.split("@")[0],
                "password": "secret123",
                "default_currency": default_currency,
            },
        )
        mark_verified(db, email)
        token = client.post(
            "/auth/token",
            data={"username": email, "password": "secret123"},
        ).json()["access_token"]

        return {"Authorization": f"Bearer {token}"}

    return _make_user