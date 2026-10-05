from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from tellspend.database.config import settings
from tellspend.database.connection import get_db
from tellspend.database.models import User

ALGORITHM = "HS256"

# Argon2 with pwdlib's recommended settings
password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/token",
)

def hash_password(password: str) -> str:
    """
    Explanation:
        Turn a password into a one-way hash for storage.

    Parameters:
        password: The plain password the user chose.

    Returns:
        The hash to store in users.password_hash.
    """
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Explanation:
        Check a login attempt against the stored hash.

    Parameters:
        password: The plain password typed at login.
        hashed_password: The hash stored for that user.

    Returns:
        True if the password matches.
    """
    return password_hash.verify(password, hashed_password)


def password_stamp(changed_at: datetime | None) -> str:
    """When the password last changed, exactly (to the microsecond), or "" if never."""
    return f"{changed_at.timestamp():.6f}" if changed_at is not None else ""


def create_access_token(user_id: int, password_changed_at: datetime | None = None) -> str:
    """
    Explanation:
        Create the signed login token. It carries when the password last
        changed, so a later change signs it out, even within the same
        second.

    Parameters:
        user_id: The user the token is for.
        password_changed_at: When their password last changed (None: never).

    Returns:
        The encoded JWT.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes,
    )

    payload = {
        "sub": str(user_id),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": expires_at,
        "pwc": password_stamp(password_changed_at),
    }

    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Explanation:
        FastAPI dependency that turns the request's token into the signed-in
        user. Any problem (bad, expired or unknown token) gives the same 401,
        so the response never reveals which part failed.

    Parameters:
        token: The bearer token from the Authorization header.
        db: The database session for this request.

    Returns:
        The signed-in user.

    Raises:
        HTTPException: 401 if the token is missing, invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        issued_at = int(payload.get("iat", 0))
        stamp = payload.get("pwc")
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise credentials_exception

    user = db.get(User, user_id)

    if user is None:
        raise credentials_exception

    # A password change signs out every login from before it.
    if stamp is not None:
        if stamp != password_stamp(user.password_changed_at):
            raise credentials_exception
    elif user.password_changed_at is not None and issued_at < int(user.password_changed_at.timestamp()):
        # A token from before stamps were added.
        raise credentials_exception

    # An account can't be used until its email is verified.
    if user.email_verified_at is None:
        raise credentials_exception

    return user