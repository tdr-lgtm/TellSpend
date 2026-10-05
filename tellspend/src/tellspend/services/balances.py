"""
Who owes whom, per contact and currency.

For each of YOUR expenses, per person:

    net = what they paid - refunds they got back - their share

People with a positive net are owed money (creditors); people with a
negative net owe it (debtors). Each debtor pays the creditors in
proportion to how much each is owed. Only the parts between you and a
contact are your balance. With one payer this is simply:

    you paid          -> each other participant owes you their share
    a contact paid    -> you owe that contact your share
    otherwise         -> money between two other people; not your balance

Then settlements move the balance, whatever they were (a loan, a
repayment, a reimbursement), except a gift, which isn't owed back:

    they_paid_me      -> they owe you less (or you owe them more)
    i_paid_them       -> you owe them less (or they owe you more)

Positive balance: they owe you. Negative: you owe them.
"""

from collections import defaultdict
from collections.abc import Hashable, Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tellspend.api.schemas import Balance
from tellspend.database.models import Counterparty, Expense, Settlement, User
from tellspend.services.money import allocate


def expense_balances(expense: Expense) -> dict[int, Decimal]:
    """
    Explanation:
        What one expense means for your balance with each contact, using
        the rules in this module's docstring.

    Parameters:
        expense: The expense, with its payments and participants loaded.

    Returns:
        contact id -> what that contact owes you for this expense
        (negative: what you owe them). Contacts with nothing are left out.
    """
    # Rows for you have counterparty_id None, so that is your key.
    return net_with_you(
        [(p.counterparty_id, p.amount) for p in expense.payments],
        [(r.counterparty_id, r.amount) for r in expense.refunds],
        [(p.counterparty_id, p.share_amount) for p in expense.participants],
    )


def net_with_you(
    payments: Iterable[tuple[Hashable, Decimal]],
    refunds: Iterable[tuple[Hashable, Decimal]],
    shares: Iterable[tuple[Hashable, Decimal]],
) -> dict[Hashable, Decimal]:
    """
    Explanation:
        Your balance with each person from one expense's payments, refunds
        and shares, each given as (person, amount) with None for you.

    Returns:
        person -> what they owe you (negative: what you owe them).
    """
    net: dict[Hashable, Decimal] = defaultdict(Decimal)

    for person, amount in payments:
        net[person] += amount

    # Money given back after paying: that person paid that much less.
    for person, amount in refunds:
        net[person] -= amount

    for person, amount in shares:
        net[person] -= amount

    creditors = [person for person, amount in net.items() if amount > 0]
    credits = [net[person] for person in creditors]

    result: dict[Hashable, Decimal] = defaultdict(Decimal)

    for debtor, amount in net.items():
        if amount >= 0:
            continue

        # Split this debt across the creditors in proportion to what they're owed.
        for creditor, part in zip(creditors, allocate(-amount, credits)):
            if debtor is None and creditor is not None:
                result[creditor] -= part      # you owe them
            elif creditor is None and debtor is not None:
                result[debtor] += part        # they owe you

    return result


def compute_balances(db: Session, user: User) -> list[Balance]:
    """
    All-time balances with every contact: every expense's balances
    added up, then moved by settlements. Kept per currency, because
    amounts in different currencies can't be added together.

    Parameters:
        db: The database session.
        user: The signed-in user.

    Returns:
        One non-zero balance per contact and currency, biggest first.
        Positive: they owe you. Negative: you owe them.
    """
    totals: dict[tuple[int, str], Decimal] = defaultdict(Decimal)

    expenses = db.scalars(
        select(Expense)
        .where(Expense.user_id == user.id)
        .options(
            selectinload(Expense.payments),
            selectinload(Expense.participants),
            selectinload(Expense.refunds),
        )
    )

    for expense in expenses:
        for counterparty_id, amount in expense_balances(expense).items():
            totals[(counterparty_id, expense.currency)] += amount

    settlements = db.scalars(select(Settlement).where(Settlement.user_id == user.id))

    for settlement in settlements:
        # A gift isn't owed back: it moves no balance.
        if settlement.kind == "gift":
            continue

        key = (settlement.counterparty_id, settlement.currency)

        if settlement.direction == "they_paid_me":
            totals[key] -= settlement.amount
        else:
            totals[key] += settlement.amount

    names = dict(
        db.execute(
            select(Counterparty.id, Counterparty.name).where(
                Counterparty.owner_user_id == user.id
            )
        ).all()
    )

    balances = [
        Balance(
            counterparty_id=counterparty_id,
            name=names.get(counterparty_id, "Unknown"),
            currency=currency,
            amount=amount,
        )
        for (counterparty_id, currency), amount in totals.items()
        if amount != 0
    ]

    # Biggest amounts first, whichever direction.
    return sorted(balances, key=lambda balance: (-abs(balance.amount), balance.name))
