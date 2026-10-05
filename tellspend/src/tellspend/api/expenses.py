from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tellspend.api.auth import get_current_user
from tellspend.api.schemas import ExpenseCreate, ExpenseResponse, ExpenseToSettlement, SettlementResponse
from tellspend.database.connection import get_db
from tellspend.database.models import Expense, ExpenseItem, Settlement, User
from tellspend.categories import Category
from tellspend.services.expense_writer import write_expense
from tellspend.services.ownership import get_owned_counterparty, get_owned_expense

router = APIRouter(
    prefix="/expenses",
    tags=["expenses"],
)

@router.get("", response_model=list[ExpenseResponse])
def list_expenses(
    category: Category | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Your expenses, newest first, optionally only one category.
        Expenses on the same day are ordered by when they were added.

    Parameters:
        category: Only expenses in this category (?category=groceries).
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The matching expenses, or 422 for an unknown category.
    """
    # selectinload: fetch every expense's payments and shares in one extra
    # query each, instead of one query per expense (the "N+1" problem).
    query = (
        select(Expense)
        .where(Expense.user_id == current_user.id)
        .options(
            selectinload(Expense.payments),
            selectinload(Expense.participants),
            selectinload(Expense.items).selectinload(ExpenseItem.owners),
            selectinload(Expense.charges),
            selectinload(Expense.deductions),
            selectinload(Expense.refunds),
            selectinload(Expense.settlements),
        )
    )

    if category is not None:
        query = query.where(Expense.category == category)

    return db.scalars(
        query.order_by(Expense.date.desc(), Expense.id.desc())
    ).all()

@router.post(
    "",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_expense(
    expense_data: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Record a new expense. Without a currency, the user's default
    currency is used; without payments or shares, the user paid all
    of it and it was all theirs.

    Parameters:
        expense_data: The full expense, including who paid and who shares.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The new expense (201), or 404 if a contact isn't the user's.
    """
    expense = write_expense(db, current_user, expense_data)
    db.commit()
    db.refresh(expense)

    return expense

@router.get("/{expense_id}", response_model=ExpenseResponse)
def get_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    One of your expenses.

    Parameters:
        expense_id: The expense to return.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The expense, or 404.
    """
    return get_owned_expense(db, current_user, expense_id)


@router.put("/{expense_id}", response_model=ExpenseResponse)
def replace_expense(
    expense_id: int,
    expense_data: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Edit an expense by replacing all its fields, payments and shares
        with the ones sent. Anything left out gets the same default as on
        create.

    Parameters:
        expense_id: The expense to replace.
        expense_data: The full new version of the expense.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The updated expense, or 404.
    """
    expense = get_owned_expense(db, current_user, expense_id)

    write_expense(db, current_user, expense_data, expense)
    db.commit()
    db.refresh(expense)

    return expense


@router.post("/{expense_id}/to-settlement", response_model=SettlementResponse, status_code=201)
def expense_to_settlement(
    expense_id: int,
    body: ExpenseToSettlement,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Turn an expense that wasn't a purchase (e.g. one saved as
        "Repayment") into the money between you and a contact that it was:
        a settlement for the same amount, currency and date, keeping its
        description as the note. The expense is removed, in the same
        transaction, so it stops counting as spending.

    Parameters:
        expense_id: The expense.
        body: Who it was with, which way the money went, and what it was.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The new settlement (201), or 404.
    """
    expense = get_owned_expense(db, current_user, expense_id)
    get_owned_counterparty(db, current_user, body.counterparty_id)
    if expense.amount is None or expense.amount <= 0:
        raise HTTPException(status_code=422, detail="This expense has no amount to move.")

    # Only an expense between you and that one contact can be money
    # between you two: one shared or paid by anyone else is a real
    # purchase, which turning it would lose.
    people = {p.counterparty_id for p in expense.payments} | {p.counterparty_id for p in expense.participants}
    people |= {r.counterparty_id for r in expense.refunds}
    if not people <= {None, body.counterparty_id}:
        raise HTTPException(
            status_code=422,
            detail="Others paid for or share this expense, so it can't become money with one person. Edit it instead.",
        )
    # What actually moved: the bill less anything given back.
    moved = expense.amount - sum((r.amount for r in expense.refunds), Decimal("0"))
    if moved <= 0:
        raise HTTPException(status_code=422, detail="All of it was given back, so there's nothing to move.")

    settlement = Settlement(
        user_id=current_user.id,
        counterparty_id=body.counterparty_id,
        direction=body.direction,
        kind=body.kind,
        amount=moved,
        currency=expense.currency,
        date=expense.date,
        note=(expense.description or None),
    )
    db.add(settlement)
    db.delete(expense)
    db.commit()
    db.refresh(settlement)
    return settlement


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: int,
    with_settlements: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Delete one of your expenses for good. Repayments saved as settling
        it are deleted too when asked (?with_settlements=true); otherwise
        they stay, no longer linked to it.

    Parameters:
        expense_id: The expense to delete.
        with_settlements: Also delete the repayments that settle it.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        Nothing (204), or 404.
    """
    expense = get_owned_expense(db, current_user, expense_id)

    if with_settlements:
        for settlement in list(expense.settlements):
            db.delete(settlement)

    db.delete(expense)
    db.commit()