"""
Single-use secrets sent by email: a 6-digit code to verify an address, and
a link to reset a password.

The link carries a random token; the database keeps only its SHA-256, so
the stored value can't be turned back into a working link. A token works
once, until it expires, and only for its purpose. Issuing a new one
retires the user's older unused ones of the same kind, so only the latest
email works.
"""

import datetime as dt
import hashlib
import hmac
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from tellspend.database.config import settings
from tellspend.database.models import AuthToken, User

VERIFY_EMAIL = "verify_email"
RESET_PASSWORD = "reset_password"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def issue_token(db: Session, user: User, purpose: str, lifetime: dt.timedelta) -> str:
    """
    Explanation:
        Create a new link token for the user, retiring their older unused
        ones for the same purpose. Adds to the session; the caller commits.

    Parameters:
        db: The database session.
        user: Who the link is for.
        purpose: VERIFY_EMAIL or RESET_PASSWORD.
        lifetime: How long it works.

    Returns:
        The token to put in the link (never stored as is).
    """
    now = _now()

    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    token = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=_hash(token),
            expires_at=now + lifetime,
        )
    )

    return token


def use_token(db: Session, token: str, purpose: str) -> User | None:
    """
    Explanation:
        Spend a link token: if it exists, is for this purpose, hasn't been
        used and hasn't expired, mark it used and return its user. Every
        other case gives None, without saying which. The caller commits.

    Parameters:
        db: The database session.
        token: The token from the link.
        purpose: What it must be for.

    Returns:
        The user, or None.
    """
    found = db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == _hash(token),
            AuthToken.purpose == purpose,
        )
    )

    now = _now()

    if found is None or found.used_at is not None or found.expires_at <= now:
        return None

    found.used_at = now

    return db.get(User, found.user_id)


def _code_hash(salt: str, code: str) -> str:
    # Keyed with the server's secret: 6 digits alone would be quick to guess
    # from a copy of the database.
    return hmac.new(settings.secret_key.encode(), f"{salt}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_code(db: Session, user: User, purpose: str, lifetime: dt.timedelta) -> str:
    """
    Explanation:
        Create a new 6-digit code for the user, retiring their older unused
        ones for the same purpose. Adds to the session; the caller commits.

    Parameters:
        db: The database session.
        user: Who the code is for.
        purpose: What it's for (VERIFY_EMAIL).
        lifetime: How long it works.

    Returns:
        The code to email (never stored as is).
    """
    now = _now()

    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(16)
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            salt=salt,
            token_hash=_code_hash(salt, code),
            expires_at=now + lifetime,
        )
    )

    return code


def check_code(db: Session, user: User, purpose: str, code: str) -> str:
    """
    Explanation:
        Check a code the user typed against their latest one. A right code
        is used up; a wrong one counts as a try, and after the allowed
        number of wrong tries the code stops working. The caller commits.

    Parameters:
        db: The database session.
        user: Whose code it is.
        purpose: What it's for.
        code: What the user typed.

    Returns:
        "ok", "wrong" (tries remain), or "expired" (no working code: it
        expired, was used, or had too many wrong tries).
    """
    now = _now()
    found = db.scalar(
        select(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.salt.is_not(None),
        )
        .order_by(AuthToken.id.desc())
        .limit(1)
    )

    if found is None or found.expires_at <= now:
        return "expired"

    if hmac.compare_digest(found.token_hash, _code_hash(found.salt or "", code)):
        found.used_at = now
        return "ok"

    found.attempts += 1
    if found.attempts >= settings.verify_code_attempts:
        found.used_at = now
        return "expired"

    return "wrong"


def sent_recently(db: Session, user: User, purpose: str, seconds: int) -> bool:
    """True if a link of this kind was sent to the user in the last `seconds`."""
    latest = db.scalar(
        select(AuthToken.created_at)
        .where(AuthToken.user_id == user.id, AuthToken.purpose == purpose)
        .order_by(AuthToken.created_at.desc())
        .limit(1)
    )

    return latest is not None and latest > _now() - dt.timedelta(seconds=seconds)
