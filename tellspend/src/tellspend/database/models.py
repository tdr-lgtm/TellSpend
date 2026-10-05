import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from tellspend.categories import DEFAULT_CATEGORY, category_check_sql
from tellspend.charges import charge_kind_check_sql
from tellspend.deductions import deduction_kind_check_sql
from tellspend.payment_methods import payment_method_check_sql

class Base(DeclarativeBase):
    pass


class User(Base):
    # An account: someone who signs in and records their own expenses.

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    # How the user is shown in the app ("Hi, XYZ").
    name: Mapped[str] = mapped_column(
        String(100),
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
    )

    default_currency: Mapped[str] = mapped_column(
        String(3),
    )

    # When the user proved they own the email (NULL: not yet).
    email_verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    # When the password last changed; login tokens issued before it no
    # longer work (so a reset signs out every other device).
    password_changed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AuthToken(Base):
    """
    A single-use secret sent by email: a 6-digit code to verify the
    address, or a link to reset the password. Only a hash is stored, so a
    copy of the database can't be used to take over accounts. A code is
    short, so it's hashed with a per-code salt and the server's secret key,
    and it stops working after a few wrong tries.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # "verify_email" or "reset_password".
    purpose: Mapped[str] = mapped_column(
        String(20),
    )

    # SHA-256 of the link token, or HMAC-SHA-256 of salt + code; hex.
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
    )

    # Codes only: a random salt for the hash, and the wrong tries so far.
    salt: Mapped[str | None] = mapped_column(
        String(32),
    )

    attempts: Mapped[int] = mapped_column(
        default=0,
        server_default="0",
    )

    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
    )

    # Set when used, or when a newer link of the same kind replaced it.
    used_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name="ck_auth_tokens_purpose_valid",
        ),
    )


class Expense(Base):
    # One bill or purchase recorded by a user.

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )

    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "counterparties.id",
            name="fk_expenses_counterparty_id_counterparties",
        ),
        index=True,
    )

    # The day the money was spent (not when it was recorded).
    date: Mapped[dt.date] = mapped_column(
        Date,
    )

    # The three amounts of a bill:
    #
    #     original_amount   before deductions
    #   - discount_amount   what deductions took off in total: the sum of
    #                       the deduction lines (discounts, rounding
    #                       down), each kept as its own kind
    #   = amount            what was actually charged; payments add up to
    #                       this
    #
    # Refunds are money given back after paying, each its own event with
    # who received it. The cost that was shared is what's left:
    #
    #     amount - refunds = the shares
    #
    # Items keep their full prices, and charges (tax, fees, tips) are kept
    # apart from them, so when items are listed:
    #
    #     items - discount_amount + charges = amount
    #
    # Exact decimal money: up to 9,999,999,999.99. Never a float.
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0"),
        server_default="0",
    )

    # Computed by the database, so it can never disagree with the other two.
    original_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        Computed("amount + discount_amount", persisted=True),
    )

    currency: Mapped[str] = mapped_column(
        String(3),
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
    )

    category: Mapped[str] = mapped_column(
        String(30),
        default=DEFAULT_CATEGORY,
        server_default=DEFAULT_CATEGORY,
        index=True,
    )

    # Anything worth keeping about it ("an estimate", "repeats every month").
    note: Mapped[str | None] = mapped_column(
        String(500),
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # onupdate: SQLAlchemy sets this again on every UPDATE of the row.
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Repayments saved as settling this expense. Deleting the expense
    # leaves them, unlinked, unless the user deletes them too.
    settlements: Mapped[list["Settlement"]] = relationship(
        back_populates="expense",
        passive_deletes=True,
        order_by="Settlement.id",
    )

    @property
    def settlement_ids(self) -> list[int]:
        return [settlement.id for settlement in self.settlements]

     # Who paid. Always adds up to `amount`.
    payments: Mapped[list["ExpensePayment"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpensePayment.id",
    )

    # Whose cost it was, and each person's share. Always adds up to `amount`.
    participants: Mapped[list["ExpenseParticipant"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseParticipant.id",
    )

    # What was bought, line by line. Optional; when given,
    # items - discount_amount + charges = amount.
    items: Mapped[list["ExpenseItem"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseItem.id",
    )

    # What was added on top of the items: tax, service charge, delivery,
    # tips, fees. Never items (nothing was bought).
    charges: Mapped[list["ExpenseCharge"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseCharge.id",
    )

    # What was taken off the price, line by line: discounts, rounding
    # down. They add up to discount_amount.
    deductions: Mapped[list["ExpenseDeduction"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseDeduction.id",
    )

    # Money given back after paying (returns, cancelled items), each with
    # who got it. The shares add up to amount minus these.
    refunds: Mapped[list["ExpenseRefund"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseRefund.id",
    )

    __table_args__ = (
            CheckConstraint(
                "amount > 0",
                name="ck_expenses_amount_positive",
            ),
            CheckConstraint(
                "discount_amount >= 0",
                name="ck_expenses_discount_non_negative",
            ),
            CheckConstraint(
                category_check_sql(),
                name="ck_expenses_category_valid",
            ),
            
            # "My expenses, newest first" is the most common query.
            Index("ix_expenses_user_id_date", "user_id", "date"),
        )

class Counterparty(Base):
    """
    A person, business, or organization in ONE user's address book.

    Every counterparty belongs to exactly one owner. Two users who both
    know "Parth" each have their own Parth row; they are never shared.
    """

    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    # Whose address book this is. Deleting the user deletes their contacts.
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
    )

    # PERSON, BUSINESS or ORGANIZATION (see the CHECK below).
    counterparty_type: Mapped[str] = mapped_column(
        String(20),
    )

    # How this person relates to the owner ("wife", "flatmate"), stored
    # lowercase, so the assistant can later recognise "my wife".
    relation: Mapped[str | None] = mapped_column(
        String(50),
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "counterparty_type IN ('PERSON', 'BUSINESS', 'ORGANIZATION')",
            name="ck_counterparties_type_valid",
        ),
    )

class ExpensePayment(Base):
    """
    Money one payer handed over for an expense.

    Paying is not owing: who is responsible for how much is recorded
    separately, as participant shares.
    """

    __tablename__ = "expense_payments"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"),
        index=True,
    )

    # Exactly one of these two is set: the owner (user_id) or one of the
    # owner's contacts (counterparty_id).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
    )

    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"),
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    # How it was paid: one of payment_methods.py, or NULL if not said.
    method: Mapped[str | None] = mapped_column(
        String(30),
    )

    # The bank, card issuer or app, e.g. "HDFC", "GPay".
    provider: Mapped[str | None] = mapped_column(
        String(100),
    )

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NULL) <> (counterparty_id IS NULL)",
            name="ck_expense_payments_one_payer",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_expense_payments_amount_positive",
        ),
        CheckConstraint(
            payment_method_check_sql(),
            name="ck_expense_payments_method_valid",
        ),
        # No one-payer-once rule: one person can pay in parts, e.g. 3,850
        # by card and 1,000 in cash on the same bill.
    )

    expense: Mapped["Expense"] = relationship(
        back_populates="payments",
    )


class ExpenseParticipant(Base):
    """Someone who shares the cost of an expense, and their share."""

    __tablename__ = "expense_participants"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"),
        index=True,
    )

    # Exactly one of these two is set, as with payments.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
    )

    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"),
        index=True,
    )

    share_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NULL) <> (counterparty_id IS NULL)",
            name="ck_expense_participants_one_person",
        ),
        CheckConstraint(
            "share_amount > 0",
            name="ck_expense_participants_share_positive",
        ),
        # Each person at most once per expense. (NULLs never clash in a
        # unique constraint, so contact rows don't collide on user_id.)
        UniqueConstraint(
            "expense_id",
            "user_id",
            name="uq_expense_participants_user",
        ),
        UniqueConstraint(
            "expense_id",
            "counterparty_id",
            name="uq_expense_participants_counterparty",
        ),
    )

    expense: Mapped["Expense"] = relationship(
        back_populates="participants",
    )


class ExpenseItem(Base):
    """One line on a bill: what was bought, how much of it, and its price."""

    __tablename__ = "expense_items"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"),
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
    )

    # 3 decimals so measured quantities fit: 1.5 kg, 0.25 l.
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
        default=Decimal("1"),
        server_default="1",
    )

    # What the quantity is counted or measured in ("kg", "bags"); NULL when
    # none was given.
    unit: Mapped[str | None] = mapped_column(
        String(20),
    )

    # The line's total price, before any discount.
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    # The price of one unit, when known (stated, or the line divides into
    # it exactly); NULL otherwise.
    unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
    )

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_expense_items_quantity_positive",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_expense_items_amount_positive",
        ),
        CheckConstraint(
            "unit_price IS NULL OR unit_price > 0",
            name="ck_expense_items_unit_price_positive",
        ),
    )

    expense: Mapped["Expense"] = relationship(
        back_populates="items",
    )

    # Whose the item is, and how much of its price each owns. Empty when
    # that wasn't said (never guessed).
    owners: Mapped[list["ExpenseItemOwner"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ExpenseItemOwner.id",
    )


class ExpenseItemOwner(Base):
    """
    Someone an item on a bill belongs to, and how much of its price is
    theirs: "the burger was Parth's", or the pizza shared by three.
    """

    __tablename__ = "expense_item_owners"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("expense_items.id", ondelete="CASCADE"),
        index=True,
    )

    # Exactly one of these: the owner (user_id) or one of their contacts.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
    )

    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"),
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NULL) <> (counterparty_id IS NULL)",
            name="ck_expense_item_owners_one_owner",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_expense_item_owners_amount_positive",
        ),
    )

    item: Mapped["ExpenseItem"] = relationship(
        back_populates="owners",
    )


class ExpenseCharge(Base):
    """
    Something a bill adds on top of what was bought: a tax (GST, VAT), a
    service charge, delivery, packaging, a tip, a fee or rounding up.
    """

    __tablename__ = "expense_charges"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"),
        index=True,
    )

    # One of charges.py.
    kind: Mapped[str] = mapped_column(
        String(30),
    )

    # As the bill names it, e.g. "CGST 9%", "Convenience fee".
    label: Mapped[str] = mapped_column(
        String(100),
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    __table_args__ = (
        CheckConstraint(
            charge_kind_check_sql(),
            name="ck_expense_charges_kind_valid",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_expense_charges_amount_positive",
        ),
    )

    expense: Mapped["Expense"] = relationship(
        back_populates="charges",
    )


class ExpenseDeduction(Base):
    """
    Something taken off a bill's price: a discount (coupon, offer,
    cashback) or rounding down. Each kind is its own line. Refunds are
    not deductions; see ExpenseRefund.
    """

    __tablename__ = "expense_deductions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"),
        index=True,
    )

    # One of deductions.py.
    kind: Mapped[str] = mapped_column(
        String(30),
    )

    # As the bill names it, e.g. "Coupon SAVE50", "Returned shirt".
    label: Mapped[str] = mapped_column(
        String(100),
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    __table_args__ = (
        CheckConstraint(
            deduction_kind_check_sql(),
            name="ck_expense_deductions_kind_valid",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_expense_deductions_amount_positive",
        ),
    )

    expense: Mapped["Expense"] = relationship(
        back_populates="deductions",
    )


class ExpenseRefund(Base):
    """
    Money given back for part of an expense after it was paid, e.g. a
    returned item: its own event, never a discount or a payment. It goes
    back to one person (usually whoever paid), which is what balances use.
    """

    __tablename__ = "expense_refunds"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"),
        index=True,
    )

    # Who got the money back: exactly one of the owner (user_id) or one of
    # the owner's contacts (counterparty_id).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
    )

    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"),
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    # What it was for, e.g. "Returned one shirt". Optional.
    label: Mapped[str | None] = mapped_column(
        String(100),
    )

    # When the money came back (can be after the expense's date).
    date: Mapped[dt.date] = mapped_column(
        Date,
    )

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NULL) <> (counterparty_id IS NULL)",
            name="ck_expense_refunds_one_recipient",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_expense_refunds_amount_positive",
        ),
    )

    expense: Mapped["Expense"] = relationship(
        back_populates="refunds",
    )


class Settlement(Base):
    """
    Money that moved between the user and one contact outside a purchase,
    e.g. "Parth paid me back 450" or "I lent Parth 1,000".

    direction (who handed it over):
        they_paid_me   the contact paid the user
        i_paid_them    the user paid the contact

    kind (what it was):
        repayment      paying back what was owed
        loan           lending: the one who got it now owes it
        reimbursement  paying someone back for an expense
        gift           given, not owed: moves no balance
        balance        no money moved: a debt that already existed
                       ("Parth owed me 600"), recorded as if the one
                       who is owed had handed it over

    Every kind but a gift moves the balance the same way: whoever handed
    money over (or is owed it) is owed that much more (or owes less).
    """

    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # No ondelete: a contact with settlements can't be deleted, like one
    # used in an expense (the API turns that into a 409).
    counterparty_id: Mapped[int] = mapped_column(
        ForeignKey("counterparties.id"),
        index=True,
    )

    direction: Mapped[str] = mapped_column(
        String(20),
    )

    kind: Mapped[str] = mapped_column(
        String(20),
        default="repayment",
        server_default="repayment",
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
    )

    currency: Mapped[str] = mapped_column(
        String(3),
    )

    date: Mapped[dt.date] = mapped_column(
        Date,
    )

    note: Mapped[str | None] = mapped_column(
        String(255),
    )

    # The expense this pays back, when it was saved as settling one.
    expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="SET NULL"),
        index=True,
    )

    expense: Mapped["Expense | None"] = relationship(
        back_populates="settlements",
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_settlements_amount_positive",
        ),
        CheckConstraint(
            "direction IN ('they_paid_me', 'i_paid_them')",
            name="ck_settlements_direction_valid",
        ),
    )


class ExpectedMoney(Base):
    """
    Money expected between the user and one contact that hasn't moved
    ("Parth will pay me back 500 next week"). It changes no balance; when
    it happens it becomes a Settlement and this row goes.

    direction:
        they_pay_me    the contact is to pay the user
        i_pay_them     the user is to pay the contact
    """

    __tablename__ = "expected_money"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # No ondelete: like settlements, a contact with these can't be deleted.
    counterparty_id: Mapped[int] = mapped_column(
        ForeignKey("counterparties.id"),
        index=True,
    )

    direction: Mapped[str] = mapped_column(
        String(20),
    )

    kind: Mapped[str] = mapped_column(
        String(20),
        default="repayment",
        server_default="repayment",
    )

    # Not always known ("the rest").
    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
    )

    currency: Mapped[str] = mapped_column(
        String(3),
    )

    due_date: Mapped[dt.date | None] = mapped_column(
        Date,
    )

    note: Mapped[str | None] = mapped_column(
        String(255),
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "amount IS NULL OR amount > 0",
            name="ck_expected_money_amount_positive",
        ),
        CheckConstraint(
            "direction IN ('they_pay_me', 'i_pay_them')",
            name="ck_expected_money_direction_valid",
        ),
    )
