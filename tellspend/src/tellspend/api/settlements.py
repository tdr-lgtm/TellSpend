"""
Routes for balances (who owes whom) and settlements (money paid back
between you and a contact).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from tellspend.api.auth import get_current_user
from tellspend.api.schemas import Balance, SettlementCreate, SettlementResponse
from tellspend.database.connection import get_db
from tellspend.database.models import Settlement, User
from tellspend.services.balances import compute_balances
from tellspend.services.ownership import get_owned_counterparty

router = APIRouter(
    tags=["balances"],
)

@router.get("/balances", response_model=list[Balance])
def get_balances(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Who owes whom, per contact and currency, after settlements.

    Parameters:
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        One non-zero balance per contact and currency. Positive amount:
        they owe you. Negative: you owe them.
    """
    return compute_balances(db, current_user)


@router.get("/settlements", response_model=list[SettlementResponse])
def list_settlements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Your settlements, newest first.

    Parameters:
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The user's settlements.
    """
    return db.scalars(
        select(Settlement)
        .where(Settlement.user_id == current_user.id)
        .order_by(Settlement.date.desc(), Settlement.id.desc())
    ).all()


@router.post(
    "/settlements",
    response_model=SettlementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_settlement(
    settlement_data: SettlementCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Record money paid back, e.g. "Parth paid me back 450".

    Parameters:
        settlement_data: The contact, direction, amount, currency and date.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The new settlement (201), or 404 if the contact isn't yours.
    """
    get_owned_counterparty(db, current_user, settlement_data.counterparty_id)

    settlement = Settlement(
        user_id=current_user.id,
        counterparty_id=settlement_data.counterparty_id,
        direction=settlement_data.direction,
        kind=settlement_data.kind,
        amount=settlement_data.amount,
        currency=settlement_data.currency or current_user.default_currency,
        date=settlement_data.date,
        note=settlement_data.note,
    )

    db.add(settlement)
    db.commit()
    db.refresh(settlement)

    return settlement


@router.put("/settlements/{settlement_id}", response_model=SettlementResponse)
def update_settlement(
    settlement_id: int,
    settlement_data: SettlementCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Change one of your settlements: who, which way, what it was, how
        much, when.

    Parameters:
        settlement_id: The settlement to change.
        settlement_data: Its new values (all of them).
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The updated settlement, or 404.
    """
    settlement = db.scalar(
        select(Settlement).where(Settlement.id == settlement_id, Settlement.user_id == current_user.id)
    )
    if settlement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement not found.")
    get_owned_counterparty(db, current_user, settlement_data.counterparty_id)

    settlement.counterparty_id = settlement_data.counterparty_id
    settlement.direction = settlement_data.direction
    settlement.kind = settlement_data.kind
    settlement.amount = settlement_data.amount
    settlement.currency = settlement_data.currency or current_user.default_currency
    settlement.date = settlement_data.date
    settlement.note = settlement_data.note
    db.commit()
    db.refresh(settlement)
    return settlement


@router.delete("/settlements/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_settlement(
    settlement_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Delete one of your settlements, e.g. one recorded by mistake.

    Parameters:
        settlement_id: The settlement to delete.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        Nothing (204), or 404.
    """
    settlement = db.scalar(
        select(Settlement).where(
            Settlement.id == settlement_id,
            Settlement.user_id == current_user.id,
        )
    )

    if settlement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settlement not found.",
        )

    db.delete(settlement)
    db.commit()
