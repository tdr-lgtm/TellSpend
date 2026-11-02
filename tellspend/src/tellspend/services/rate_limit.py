"""
How often one user may ask the assistant: each read calls a paid model,
so a runaway client (or a loop of retries) mustn't spend the budget.
Counted in this process's memory, per user, over the last minute and
the last day (settings.assistant_requests_per_minute / _per_day).
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from tellspend.database.config import settings

MINUTE = 60
DAY = 24 * 60 * 60

_lock = threading.Lock()
_calls: dict[int, deque[float]] = defaultdict(deque)


def check_assistant_limit(user_id: int, now: float | None = None) -> None:
    """
    Explanation:
        Count one assistant read for the user, or refuse it when they've
        reached a limit. Calls older than a day are forgotten.

    Parameters:
        user_id: Who is asking.
        now: The time (for tests); the current time when left out.

    Raises:
        HTTPException 429 when the per-minute or per-day limit is reached.
    """
    now = time.time() if now is None else now

    with _lock:
        calls = _calls[user_id]
        while calls and calls[0] <= now - DAY:
            calls.popleft()

        last_minute = sum(1 for at in calls if at > now - MINUTE)
        if last_minute >= settings.assistant_requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="That's a lot of requests in a minute. Wait a moment and try again.",
            )
        if len(calls) >= settings.assistant_requests_per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You've reached today's limit for the assistant. You can still add expenses by hand.",
            )

        calls.append(now)


def reset() -> None:
    """Forget every count (for tests)."""
    with _lock:
        _calls.clear()


# ---------- wrong passwords on login ----------
# Failed logins, per (email, client) and per email, over the last
# settings.login_window_minutes. Counted in this process's memory like the
# assistant limit: a restart forgets them, which only ever unlocks early.

_failures: dict[tuple, deque[float]] = defaultdict(deque)


def client_address(request) -> str:
    """The client's address: from X-Forwarded-For only behind a trusted proxy."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _recent(key: tuple, now: float) -> deque[float]:
    window = settings.login_window_minutes * MINUTE
    times = _failures[key]
    while times and times[0] <= now - window:
        times.popleft()
    return times


def check_login_allowed(email: str, address: str, now: float | None = None) -> None:
    """
    Explanation:
        Refuse a login attempt while there have been too many wrong
        passwords for this email, from this client or from everywhere.
        Checked before the password, so a locked account gives no hint
        whether a guess was right.

    Parameters:
        email: The email being signed in to (normalized).
        address: The client's address.
        now: The time (for tests); the current time when left out.

    Raises:
        HTTPException 429, with Retry-After, while locked.
    """
    now = time.time() if now is None else now
    window = settings.login_window_minutes * MINUTE

    with _lock:
        locked_until = []
        for key, limit in (
            (("pair", email, address), settings.login_max_failures),
            (("email", email), settings.login_max_failures_per_account),
        ):
            times = _recent(key, now)
            if len(times) >= limit:
                # Unlocks when enough failures have aged out of the window.
                locked_until.append(times[len(times) - limit] + window)

    if locked_until:
        wait = max(1, int(max(locked_until) - now + 0.999))
        minutes = max(1, -(-wait // MINUTE))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many wrong passwords for this account. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}, or reset your password."
            ),
            headers={"Retry-After": str(wait)},
        )


def record_login_failure(email: str, address: str, now: float | None = None) -> None:
    """Count one wrong password (or unknown email) for this email and client."""
    now = time.time() if now is None else now
    with _lock:
        for key in (("pair", email, address), ("email", email)):
            _recent(key, now).append(now)
        # Forget keys nobody has failed on lately, so memory stays small.
        if len(_failures) > 10_000:
            for key in [k for k, v in _failures.items() if not v or v[-1] <= now - DAY]:
                del _failures[key]


def record_login_success(email: str, address: str) -> None:
    """The right password: this client's failures for the email are forgiven."""
    with _lock:
        _failures.pop(("pair", email, address), None)


def reset_login_failures() -> None:
    """Forget every failed login (for tests)."""
    with _lock:
        _failures.clear()
