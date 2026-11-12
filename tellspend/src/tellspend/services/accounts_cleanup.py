"""
Sign-ups whose email was never verified are removed after
settings.unverified_account_hours. They can't sign in, so they hold no
data; keeping them would only keep their email looking taken and the
users table growing with abandoned and mistyped sign-ups.

Run at each sign-up and when the server starts (no scheduler needed: the
free host sleeps when idle, so a timer couldn't be relied on anyway).
"""

import datetime as dt
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tellspend.database.config import settings
from tellspend.database.models import (
    Counterparty,
    ExpectedMoney,
    Expense,
    ExpenseItemOwner,
    ExpenseParticipant,
    ExpensePayment,
    ExpenseRefund,
    Settlement,
    User,
)

logger = logging.getLogger("tellspend.accounts")


def remove_stale_unverified(db: Session, now: dt.datetime | None = None) -> int:
    """
    Explanation:
        Delete accounts that were never verified and are older than
        settings.unverified_account_hours (their codes go with them).

    Parameters:
        db: The database session.
        now: The time (for tests); the current time when left out.

    Returns:
        How many accounts were removed.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=settings.unverified_account_hours)

    # Never an account that holds anything: accounts made before email
    # verification existed are "unverified" too, and may have real data.
    holds_nothing = [
        ~select(Expense.id).where(Expense.user_id == User.id).exists(),
        ~select(Counterparty.id).where(Counterparty.owner_user_id == User.id).exists(),
        ~select(Settlement.id).where(Settlement.user_id == User.id).exists(),
        ~select(ExpectedMoney.id).where(ExpectedMoney.user_id == User.id).exists(),
        ~select(ExpenseParticipant.id).where(ExpenseParticipant.user_id == User.id).exists(),
        ~select(ExpensePayment.id).where(ExpensePayment.user_id == User.id).exists(),
        ~select(ExpenseItemOwner.id).where(ExpenseItemOwner.user_id == User.id).exists(),
        ~select(ExpenseRefund.id).where(ExpenseRefund.user_id == User.id).exists(),
    ]

    removed = db.execute(
        delete(User).where(User.email_verified_at.is_(None), User.created_at < cutoff, *holds_nothing)
    ).rowcount or 0
    db.commit()

    if removed:
        logger.info("Removed %d sign-up(s) never verified within %d hours", removed, settings.unverified_account_hours)
    return removed
