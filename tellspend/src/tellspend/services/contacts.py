"""
Merging two contacts that are the same person (e.g. "Aadhya" and "adhya"),
so their expenses, payments, shares, item owners, refunds and settlements
and expected money all belong to one contact and balances aren't split between two names.
"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from tellspend.database.models import (
    Counterparty,
    ExpectedMoney,
    Expense,
    ExpenseItem,
    ExpenseItemOwner,
    ExpenseParticipant,
    ExpensePayment,
    ExpenseRefund,
    Settlement,
    User,
)


def merge_contacts(db: Session, user: User, source: Counterparty, target: Counterparty) -> Counterparty:
    """
    Explanation:
        Move everything recorded with `source` onto `target`, then delete
        `source`. Where both are on the same expense (a share each) or the
        same item (an owner each), their amounts are added into one row,
        so every expense still adds up exactly. Only the user's own
        records are touched. The caller commits.

    Parameters:
        db: The database session.
        user: The signed-in user (owner of both contacts).
        source: The contact to merge away.
        target: The contact to keep.

    Returns:
        The kept contact.
    """
    expense_ids = select(Expense.id).where(Expense.user_id == user.id)

    # Who was paid.
    db.execute(
        update(Expense)
        .where(Expense.user_id == user.id, Expense.counterparty_id == source.id)
        .values(counterparty_id=target.id)
    )

    # Payments and refunds: several rows per person are fine.
    for model in (ExpensePayment, ExpenseRefund):
        db.execute(
            update(model)
            .where(model.expense_id.in_(expense_ids), model.counterparty_id == source.id)
            .values(counterparty_id=target.id)
        )

    # Shares: one per person per expense, so both become one.
    for share in db.scalars(
        select(ExpenseParticipant).where(
            ExpenseParticipant.expense_id.in_(expense_ids), ExpenseParticipant.counterparty_id == source.id
        )
    ).all():
        kept = db.scalar(
            select(ExpenseParticipant).where(
                ExpenseParticipant.expense_id == share.expense_id, ExpenseParticipant.counterparty_id == target.id
            )
        )
        if kept is None:
            share.counterparty_id = target.id
        else:
            kept.share_amount += share.share_amount
            db.delete(share)
    db.flush()

    # Item owners: one per person per item, likewise.
    item_ids = select(ExpenseItem.id).where(ExpenseItem.expense_id.in_(expense_ids))
    for owner in db.scalars(
        select(ExpenseItemOwner).where(
            ExpenseItemOwner.item_id.in_(item_ids), ExpenseItemOwner.counterparty_id == source.id
        )
    ).all():
        kept = db.scalar(
            select(ExpenseItemOwner).where(
                ExpenseItemOwner.item_id == owner.item_id, ExpenseItemOwner.counterparty_id == target.id
            )
        )
        if kept is None:
            owner.counterparty_id = target.id
        else:
            kept.amount += owner.amount
            db.delete(owner)
    db.flush()

    for model in (Settlement, ExpectedMoney):
        db.execute(
            update(model)
            .where(model.user_id == user.id, model.counterparty_id == source.id)
            .values(counterparty_id=target.id)
        )

    # What's known about the person carries over when the kept one lacks it.
    if not target.relation and source.relation:
        target.relation = source.relation

    db.flush()
    db.delete(source)
    return target
