"""
Routes for money expected between you and a contact that hasn't moved
yet ("Parth will pay me back 500 next week"). It changes no balance until
it's marked as happened, when it becomes a settlement.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from tellspend.api.auth import get_current_user
from tellspend.api.schemas import ExpectedDone, ExpectedResponse, SettlementResponse
from tellspend.database.connection import get_db
from tellspend.database.models import ExpectedMoney, Settlement, User

router = APIRouter(
    prefix="/expected",
    tags=["expected"],
)


def get_owned_expected(db: Session, user: User, expected_id: int) -> ExpectedMoney:
    """The user's expected money with this id, or 404."""
    expected = db.scalar(
        select(ExpectedMoney).where(ExpectedMoney.id == expected_id, ExpectedMoney.user_id == user.id)
    )
    if expected is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return expected


@router.get("", response_model=list[ExpectedResponse])
def list_expected(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Money you're still expecting to get or pay, soonest due first
        (with no date last).

    Parameters:
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The user's expected money.
    """
    return db.scalars(
        select(ExpectedMoney)
        .where(ExpectedMoney.user_id == current_user.id)
        .order_by(ExpectedMoney.due_date.asc().nulls_last(), ExpectedMoney.id)
    ).all()


@router.post("/{expected_id}/done", response_model=SettlementResponse, status_code=status.HTTP_201_CREATED)
def mark_done(
    expected_id: int,
    body: ExpectedDone,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        It happened: record it as money between you and the contact (a
        settlement, which moves the balance), for the amount expected or
        the one given, and stop expecting it. One transaction.

    Parameters:
        expected_id: The expected money.
        body: How much was actually paid (left out: as expected) and when.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The new settlement (201); 404; 422 when no amount is known.
    """
    expected = get_owned_expected(db, current_user, expected_id)
    amount = body.amount or expected.amount
    if amount is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="How much was it?")

    settlement = Settlement(
        user_id=current_user.id,
        counterparty_id=expected.counterparty_id,
        direction="they_paid_me" if expected.direction == "they_pay_me" else "i_paid_them",
        kind=expected.kind,
        amount=amount,
        currency=expected.currency,
        date=body.date,
        note=expected.note,
    )
    db.add(settlement)
    db.delete(expected)
    db.commit()
    db.refresh(settlement)
    return settlement


@router.delete("/{expected_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expected(
    expected_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Stop expecting it (it won't happen, or was a mistake).

    Parameters:
        expected_id: The expected money.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        Nothing (204), or 404.
    """
    db.delete(get_owned_expected(db, current_user, expected_id))
    db.commit()
