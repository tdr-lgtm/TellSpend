"""
Rate limits, counted in the database (the rate_events table), so a server
restart doesn't hand out fresh limits:

    assistant      each assistant read calls a paid model: per user, per
                   minute and per day (settings.assistant_requests_*)
    login_fail     wrong passwords, per (email, client) and per email, over
                   settings.login_window_minutes (a locked account stays
                   locked through a restart)
    signup /       per client address, per hour (settings.*_per_hour):
    forgot /       stops a script from flooding inboxes with codes and
    resend         links, or checking thousands of emails for accounts

Each limit counts rows newer than its window; rows older than a day are
deleted as new ones come in. Every function takes the request's database
session and commits what it records (a refused request still counts).
"""

import datetime as dt
import time

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tellspend.database.config import settings
from tellspend.database.models import RateEvent

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR


def _at(now: float | None) -> dt.datetime:
    return dt.datetime.fromtimestamp(time.time() if now is None else now, dt.timezone.utc)


def _count(db: Session, bucket: str, key: str, since: dt.datetime) -> int:
    return db.scalar(
        select(func.count()).select_from(RateEvent)
        .where(RateEvent.bucket == bucket, RateEvent.key == key, RateEvent.at > since)
    ) or 0


def _oldest_recent(db: Session, bucket: str, key: str, since: dt.datetime, nth_newest: int) -> dt.datetime | None:
    """The time of the nth newest event in the window (1 = newest)."""
    return db.scalar(
        select(RateEvent.at)
        .where(RateEvent.bucket == bucket, RateEvent.key == key, RateEvent.at > since)
        .order_by(RateEvent.at.desc())
        .offset(nth_newest - 1)
        .limit(1)
    )


def _record(db: Session, bucket: str, keys: list[str], at: dt.datetime) -> None:
    for key in keys:
        db.add(RateEvent(bucket=bucket, key=key[:400], at=at))
    # Nothing is limited over more than a day: older rows can go.
    db.execute(delete(RateEvent).where(RateEvent.at < at - dt.timedelta(seconds=DAY)))
    db.commit()


def _refuse(detail: str, wait: float | None = None) -> HTTPException:
    headers = {"Retry-After": str(max(1, int(wait + 0.999)))} if wait is not None else None
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail, headers=headers)


# ---------- the assistant ----------

def check_assistant_limit(db: Session, user_id: int, now: float | None = None) -> None:
    """
    Explanation:
        Count one assistant read for the user, or refuse it when they've
        reached a limit.

    Parameters:
        db: The request's database session.
        user_id: Who is asking.
        now: The time (for tests); the current time when left out.

    Raises:
        HTTPException 429 when the per-minute or per-day limit is reached.
    """
    at = _at(now)
    key = str(user_id)

    if _count(db, "assistant", key, at - dt.timedelta(seconds=MINUTE)) >= settings.assistant_requests_per_minute:
        raise _refuse("That's a lot of requests in a minute. Wait a moment and try again.")
    if _count(db, "assistant", key, at - dt.timedelta(seconds=DAY)) >= settings.assistant_requests_per_day:
        raise _refuse("You've reached today's limit for the assistant. You can still add expenses by hand.")

    _record(db, "assistant", [key], at)


# ---------- wrong passwords on login ----------

def client_address(request) -> str:
    """The client's address: from X-Forwarded-For only behind a trusted proxy."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _login_keys(email: str, address: str) -> list[tuple[str, int]]:
    return [
        (f"pair:{email}|{address}", settings.login_max_failures),
        (f"email:{email}", settings.login_max_failures_per_account),
    ]


def check_login_allowed(db: Session, email: str, address: str, now: float | None = None) -> None:
    """
    Explanation:
        Refuse a login attempt while there have been too many wrong
        passwords for this email, from this client or from everywhere.
        Checked before the password, so a locked account gives no hint
        whether a guess was right.

    Parameters:
        db: The request's database session.
        email: The email being signed in to (normalized).
        address: The client's address.
        now: The time (for tests); the current time when left out.

    Raises:
        HTTPException 429, with Retry-After, while locked.
    """
    at = _at(now)
    window = dt.timedelta(minutes=settings.login_window_minutes)

    locked_until: list[dt.datetime] = []
    for key, limit in _login_keys(email, address):
        if _count(db, "login_fail", key, at - window) >= limit:
            # Unlocks when enough failures have aged out of the window.
            oldest = _oldest_recent(db, "login_fail", key, at - window, limit)
            if oldest is not None:
                locked_until.append(oldest + window)

    if locked_until:
        wait = (max(locked_until) - at).total_seconds()
        minutes = max(1, -(-int(wait + 0.999) // MINUTE))
        raise _refuse(
            "Too many wrong passwords for this account. "
            f"Try again in {minutes} minute{'s' if minutes != 1 else ''}, or reset your password.",
            wait,
        )


def record_login_failure(db: Session, email: str, address: str, now: float | None = None) -> None:
    """Count one wrong password (or unknown email) for this email and client."""
    _record(db, "login_fail", [key for key, _ in _login_keys(email, address)], _at(now))


def record_login_success(db: Session, email: str, address: str) -> None:
    """The right password: this client's failures for the email are forgiven."""
    db.execute(delete(RateEvent).where(RateEvent.bucket == "login_fail", RateEvent.key == f"pair:{email}|{address}"))
    db.commit()


# ---------- emails sent on request: sign-up, reset link, new code ----------

_EMAIL_LIMITS = {
    "signup": ("signups_per_hour", "Too many sign-ups from this device. Try again in an hour."),
    "forgot": ("reset_requests_per_hour", "Too many reset requests from this device. Try again later."),
    "resend": ("code_requests_per_hour", "Too many code requests from this device. Try again later."),
}


def check_email_request(db: Session, action: str, address: str, now: float | None = None) -> None:
    """
    Explanation:
        Count one sign-up, reset request or new-code request from this
        client address, or refuse it once the hourly limit is reached.
        (The per-email "one a minute" limit is separate: auth_tokens.)

    Parameters:
        db: The request's database session.
        action: "signup", "forgot" or "resend".
        address: The client's address.
        now: The time (for tests); the current time when left out.

    Raises:
        HTTPException 429, with Retry-After, at the limit.
    """
    setting, message = _EMAIL_LIMITS[action]
    limit = getattr(settings, setting)
    at = _at(now)
    since = at - dt.timedelta(seconds=HOUR)

    if _count(db, action, address, since) >= limit:
        oldest = _oldest_recent(db, action, address, since, limit)
        wait = (oldest + dt.timedelta(seconds=HOUR) - at).total_seconds() if oldest else HOUR
        raise _refuse(message, wait)

    _record(db, action, [address], at)
