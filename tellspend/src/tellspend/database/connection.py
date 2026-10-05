from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tellspend.database.config import settings

# pool_pre_ping checks a pooled connection before use, so a connection the
# database dropped (restart, idle timeout) is replaced instead of failing.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

# Sessions never commit on their own; each writer commits explicitly.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

def get_db() -> Generator[Session, None, None]:
    # FastAPI dependency that opens a session for one request and always
    # closes it afterwards, even if the request fails.
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()