"""
Loading the signed-in user's own rows.

Someone else's row gives the same 404 as one that doesn't exist, so the
API never reveals which ids belong to other people.
"""

from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from tellspend.database.models import Counterparty, Expense, User


def get_owned_expense(db: Session, user: User, expense_id: int) -> Expense:
    """
    Load one of the user's own expenses.

    Parameters:
        db: The database session for this request.
        user: The signed-in user.
        expense_id: The expense to load.

    Returns:
        The expense.

    Raises:
        HTTPException 404 if it doesn't exist or isn't the user's.
    """
    expense = db.scalar(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == user.id,
        )
    )

    if expense is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found.",
        )

    return expense


def get_owned_counterparty(db: Session, user: User, counterparty_id: int) -> Counterparty:
    """
    Explanation:
        Load one of the user's own contacts.

    Parameters:
        db: The database session for this request.
        user: The signed-in user.
        counterparty_id: The contact to load.

    Returns:
        The contact.

    Raises:
        HTTPException 404 if it doesn't exist or isn't the user's.
    """
    counterparty = db.scalar(
        select(Counterparty).where(
            Counterparty.id == counterparty_id,
            Counterparty.owner_user_id == user.id,
        )
    )

    if counterparty is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found.",
        )

    return counterparty


def ensure_owned_counterparties(db: Session, user: User, counterparty_ids: Iterable[int]) -> None:
    """
    Explanation:
        Check, in one query, that every given contact id is the user's.

    Parameters:
        db: The database session for this request.
        user: The signed-in user.
        counterparty_ids: The contact ids to check (repeats are fine).

    Returns:
        None.

    Raises:
        HTTPException 404 if any of them doesn't exist or isn't the user's.
    """
    wanted = set(counterparty_ids)

    if not wanted:
        return

    found = set(
        db.scalars(
            select(Counterparty.id).where(
                Counterparty.id.in_(wanted),
                Counterparty.owner_user_id == user.id,
            )
        )
    )

    if found != wanted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found.",
        )
