"""
Monthly numbers for the overview, per currency (never mixed).

    your_spending   your share of each expense: what the month actually
                    cost YOU, not the whole bill you may have paid for others
                    (net of refunds, in the purchase's month), plus money
                    you gave as a gift this month
    you_paid        money that left your pocket this month for expenses and
                    gifts, less refunds that came back to you this month
    by_category     your spending split by category, biggest first
    owed_to_you /   all-time balances (services.balances), because a debt
    you_owe         doesn't belong to the month it started in
"""

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tellspend.api.schemas import CategoryTotal, CurrencySummary, MonthSummary
from tellspend.database.models import Expense, ExpenseRefund, Settlement, User
from tellspend.services.balances import compute_balances


def month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """
    Explanation:
        Turn a month into the date range it covers:
        "2026-09" -> (2026-09-01, 2026-10-01).

    Parameters:
        month: The month as YYYY-MM.

    Returns:
        (first day, first day of the next month); the end is exclusive.

    Raises:
        ValueError: If the month is malformed.
    """
    try:
        year_text, month_text = month.split("-")
        year, month_number = int(year_text), int(month_text)
    except ValueError:
        raise ValueError("Month must look like 2026-09.")

    if len(year_text) != 4 or len(month_text) != 2 or not 1 <= month_number <= 12:
        raise ValueError("Month must look like 2026-09.")

    start = dt.date(year, month_number, 1)
    end = dt.date(year + (month_number == 12), month_number % 12 + 1, 1)

    return start, end


def month_summary(db: Session, user: User, month: str) -> MonthSummary:
    """
    Explanation:
        The overview's numbers for one month, one entry per currency,
        since amounts in different currencies can't be added together.

    Parameters:
        db: The database session.
        user: The signed-in user.
        month: The month as YYYY-MM.

    Returns:
        The month's totals per currency, the default currency first. The
        default currency is always included, even with nothing in it.

    Raises:
        ValueError: If the month is malformed.
    """
    start, end = month_bounds(month)

    expenses = db.scalars(
        select(Expense)
        .where(
            Expense.user_id == user.id,
            Expense.date >= start,
            Expense.date < end,
        )
        .options(selectinload(Expense.payments), selectinload(Expense.participants))
    )

    spending: dict[str, Decimal] = defaultdict(Decimal)
    paid: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    by_category: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

    for expense in expenses:
        currency = expense.currency
        counts[currency] += 1

        # Rows for you have counterparty_id None.
        paid[currency] += sum(
            (p.amount for p in expense.payments if p.counterparty_id is None),
            Decimal("0"),
        )

        my_share = sum(
            (p.share_amount for p in expense.participants if p.counterparty_id is None),
            Decimal("0"),
        )

        # Only your own share counts as your spending.
        if my_share:
            spending[currency] += my_share
            by_category[currency][expense.category] += my_share

    # Money that came back to you this month, whenever it was spent.
    for refund, currency in db.execute(
        select(ExpenseRefund, Expense.currency)
        .join(Expense, ExpenseRefund.expense_id == Expense.id)
        .where(
            Expense.user_id == user.id,
            ExpenseRefund.counterparty_id.is_(None),
            ExpenseRefund.date >= start,
            ExpenseRefund.date < end,
        )
    ).all():
        paid[currency] -= refund.amount

    # Money you gave away is spent: a gift isn't owed back.
    for gift in db.scalars(
        select(Settlement).where(
            Settlement.user_id == user.id,
            Settlement.kind == "gift",
            Settlement.direction == "i_paid_them",
            Settlement.date >= start,
            Settlement.date < end,
        )
    ):
        spending[gift.currency] += gift.amount
        paid[gift.currency] += gift.amount
        by_category[gift.currency]["gifts_donations"] += gift.amount

    owed_to_you: dict[str, Decimal] = defaultdict(Decimal)
    you_owe: dict[str, Decimal] = defaultdict(Decimal)

    for balance in compute_balances(db, user):
        if balance.amount > 0:
            owed_to_you[balance.currency] += balance.amount
        else:
            you_owe[balance.currency] -= balance.amount

    currencies = set(counts) | set(spending) | set(paid) | set(owed_to_you) | set(you_owe) | {user.default_currency}

    summaries = [
        CurrencySummary(
            currency=currency,
            your_spending=spending[currency],
            you_paid=paid[currency],
            expense_count=counts[currency],
            by_category=[
                CategoryTotal(category=category, amount=amount)
                for category, amount in sorted(
                    by_category[currency].items(), key=lambda item: (-item[1], item[0])
                )
            ],
            owed_to_you=owed_to_you[currency],
            you_owe=you_owe[currency],
        )
        for currency in currencies
    ]

    # Your default currency first, then the rest alphabetically.
    summaries.sort(key=lambda summary: (summary.currency != user.default_currency, summary.currency))

    return MonthSummary(month=month, currencies=summaries)
