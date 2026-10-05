"""
The ONE place an expense is written.

Manual create and edit (and later the assistant) all end here, so the
rules for payers, shares and contacts are enforced the same way no matter
where the data came from.
"""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from tellspend.api.schemas import (
    ExpenseCreate,
    ExpenseParticipantCreate,
    ExpensePaymentCreate,
)
from tellspend.database.models import (
    Counterparty,
    Expense,
    ExpenseCharge,
    ExpenseDeduction,
    ExpenseRefund,
    ExpenseItem,
    ExpenseItemOwner,
    ExpenseParticipant,
    ExpensePayment,
    User,
)
from tellspend.services.ownership import ensure_owned_counterparties


def _person(user: User, counterparty_id: int | None) -> dict:
    """
    Explanation:
        Turn the API's way of naming a person (a contact id, or null for
        "you") into the two database columns, exactly one of them set.

    Parameters:
        user: The signed-in user.
        counterparty_id: A contact id, or None for the user.

    Returns:
        {"user_id": ..., "counterparty_id": ...}
    """
    if counterparty_id is None:
        return {"user_id": user.id, "counterparty_id": None}

    return {"user_id": None, "counterparty_id": counterparty_id}


def write_expense(
    db: Session,
    user: User,
    data: ExpenseCreate,
    expense: Expense | None = None,
) -> Expense:
    """
    Explanation:
        Write `data` into `expense` (a new one when None). The totals and
        repeats were already checked by ExpenseCreate; this checks that
        every contact is the user's and fills in the defaults. Adds to the
        session but does NOT commit; the caller owns the transaction.

    Parameters:
        db: The database session.
        user: The signed-in user, who owns the expense.
        data: The full expense to write.
        expense: The expense to replace when editing; None to create.

    Returns:
        The written (flushed, not committed) expense.

    Raises:
        HTTPException 404 if any contact isn't the user's.
    """
    # 1. Every contact mentioned anywhere must be the user's own. Checked
    #    before anything is added, so a bad request changes nothing.
    contact_ids = {data.counterparty_id}
    contact_ids.update(p.counterparty_id for p in data.payments or [])
    contact_ids.update(p.counterparty_id for p in data.participants or [])
    contact_ids.update(r.counterparty_id for r in data.refunds)
    contact_ids.update(o.counterparty_id for item in data.items for o in item.owners)
    contact_ids.discard(None)
    ensure_owned_counterparties(db, user, contact_ids)

    # A shop or business can be paid, never owe part of the cost.
    owners = {p.counterparty_id for p in data.participants or []}
    owners.update(o.counterparty_id for item in data.items for o in item.owners)
    owners.discard(None)
    if owners and db.scalar(
        select(Counterparty.id).where(Counterparty.id.in_(owners), Counterparty.counterparty_type == "BUSINESS")
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A shop or business can't have a share of the cost. Pick the people it's for.",
        )

    # 2. Defaults: you paid all of it, and it was all yours.
    payments = data.payments
    if payments is None:
        payments = [ExpensePaymentCreate(amount=data.amount)]

    # Refunds come off the cost that was shared.
    participants = data.participants
    if participants is None:
        refunded = sum((refund.amount for refund in data.refunds), Decimal("0"))
        participants = [ExpenseParticipantCreate(share_amount=data.amount - refunded)]

    # 3. Write. On edit, delete the old rows and flush first: SQLAlchemy
    #    inserts before it deletes, so re-adding the same person in one
    #    flush would hit the one-person-once unique constraint.
    if expense is None:
        expense = Expense(user_id=user.id)
        db.add(expense)
    else:
        expense.payments.clear()
        expense.participants.clear()
        expense.items.clear()
        expense.charges.clear()
        expense.deductions.clear()
        expense.refunds.clear()
        db.flush()

    expense.counterparty_id = data.counterparty_id
    expense.date = data.date
    expense.amount = data.amount
    expense.discount_amount = data.discount_amount
    expense.currency = data.currency or user.default_currency
    expense.description = data.description
    expense.category = data.category
    expense.note = data.note

    expense.payments.extend(
        ExpensePayment(
            amount=p.amount,
            method=p.method,
            provider=p.provider,
            **_person(user, p.counterparty_id),
        )
        for p in payments
    )
    expense.items.extend(
        ExpenseItem(
            name=item.name,
            quantity=item.quantity,
            unit=item.unit,
            amount=item.amount,
            unit_price=item.unit_price,
            owners=[
                ExpenseItemOwner(amount=owner.amount, **_person(user, owner.counterparty_id))
                for owner in item.owners
            ],
        )
        for item in data.items
    )
    expense.charges.extend(
        ExpenseCharge(kind=charge.kind, label=charge.label, amount=charge.amount)
        for charge in data.charges
    )
    expense.deductions.extend(
        ExpenseDeduction(kind=deduction.kind, label=deduction.label, amount=deduction.amount)
        for deduction in data.deductions
    )
    expense.refunds.extend(
        ExpenseRefund(
            amount=refund.amount,
            label=refund.label,
            date=refund.date or data.date,
            **_person(user, refund.counterparty_id),
        )
        for refund in data.refunds
    )
    expense.participants.extend(
        ExpenseParticipant(share_amount=p.share_amount, **_person(user, p.counterparty_id))
        for p in participants
    )

    db.flush()

    return expense
