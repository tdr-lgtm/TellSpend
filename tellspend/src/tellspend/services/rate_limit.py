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
