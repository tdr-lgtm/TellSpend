import re
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
import datetime as dt
from tellspend.categories import DEFAULT_CATEGORY, Category
from tellspend.charges import CHARGE_LABELS, ChargeKind
from tellspend.deductions import DEDUCTION_LABELS, DeductionKind
from tellspend.payment_methods import PaymentMethod
from typing import Literal

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def clean_currency_code(value: str) -> str:
    """
    Explanation:
        Uppercase a currency code ("inr" -> "INR") and allow only letters.
        Shared by every schema that takes a currency.

    Parameters:
        value: The currency code as sent.

    Returns:
        The uppercase code.

    Raises:
        ValueError: If it is not made of letters.
    """
    code = value.strip().upper()

    if not code.isalpha():
        raise ValueError("Currency must be a 3-letter code like INR.")

    return code

# Sign-up details
class UserCreate(BaseModel):
    email: str = Field(
        max_length=255,
    )

    name: str = Field(
        min_length=1,
        max_length=100,
    )

    # Upper limit stops someone sending a huge "password" to make hashing slow.
    password: str = Field(
        min_length=8,
        max_length=128,
    )

    default_currency: str = Field(
        default="INR",
        min_length=3,
        max_length=3,
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """
        Explanation:
            Trim and lowercase the email, so "Me@X.com " and "me@x.com"
            are the same account, and reject anything not shaped like one.

        Parameters:
            value: The email as sent.

        Returns:
            The cleaned email.

        Raises:
            ValueError: If it does not look like an email.
        """
        email = value.strip().lower()

        if not EMAIL_PATTERN.match(email):
            raise ValueError("Enter a valid email address.")

        return email

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """
        Explanation:
            Trim the name and collapse repeated spaces; a name of only
            spaces is rejected.

        Parameters:
            value: The name as sent.

        Returns:
            The cleaned name.

        Raises:
            ValueError: If nothing is left after trimming.
        """
        name = " ".join(value.split())

        if not name:
            raise ValueError("Name cannot be empty.")

        return name

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        """Store currency codes uppercase and letters-only."""
        return clean_currency_code(value)
    
class UserUpdate(BaseModel):
    # Profile changes; only the fields sent change.
    name: str | None = Field(default=None, min_length=1, max_length=100)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = " ".join(value.split())
        if not name:
            raise ValueError("Name cannot be empty.")
        return name

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return None if value is None else clean_currency_code(value)


class AccountDelete(BaseModel):
    # Deleting the account needs the password again.
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    # A user as the API returns it (never includes the password hash).
    id: int
    email: str
    name: str
    default_currency: str
    email_verified_at: dt.datetime | None = None

    @computed_field
    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    # Lets FastAPI build this straight from a User database object.
    model_config = ConfigDict(
        from_attributes=True,
    )

class Token(BaseModel):
    access_token: str
    token_type: str

class VerifyCode(BaseModel):
    # The email being verified and the 6-digit code sent to it.
    email: str = Field(
        max_length=255,
    )

    code: str = Field(
        max_length=20,
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("code")
    @classmethod
    def six_digits(cls, value: str) -> str:
        code = "".join(value.split())
        if len(code) != 6 or not code.isdigit():
            raise ValueError("Enter the 6-digit code from the email.")
        return code

class ForgotPassword(BaseModel):
    email: str = Field(
        max_length=255,
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

class ResetPassword(BaseModel):
    token: str = Field(
        min_length=1,
        max_length=200,
    )

    # The same rules as signing up.
    password: str = Field(
        min_length=8,
        max_length=128,
    )

class Message(BaseModel):
    # A plain answer for the user.
    detail: str

# Who paid and who shares the cost. A person is named by counterparty_id:
# one of your contacts, or null for you.


def clean_optional_text(value: str | None) -> str | None:
    """Trim and collapse spaces; blank means not given (None)."""
    if value is None:
        return None

    return " ".join(value.split()) or None


class ExpensePaymentCreate(BaseModel):
    """
    Money one payer handed over. counterparty_id null means you. The same
    person may appear twice, e.g. part by card and part in cash.
    """

    counterparty_id: int | None = None

    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    method: PaymentMethod | None = None

    # The bank, card issuer or app, e.g. "HDFC", "GPay".
    provider: str | None = Field(
        default=None,
        max_length=100,
    )

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: object) -> object:
        """Accept the method in any case ("UPI" -> "upi"); blank means not given."""
        if isinstance(value, str):
            return value.strip().lower() or None

        return value

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ExpenseItemOwnerCreate(BaseModel):
    """Someone an item belongs to, and how much of its price. Null means you."""

    counterparty_id: int | None = None

    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )


class ExpenseItemCreate(BaseModel):
    """One line on a bill: what, how much of it, and the line's total price."""

    name: str = Field(
        max_length=255,
    )

    quantity: Decimal = Field(
        default=Decimal("1"),
        gt=0,
        max_digits=10,
        decimal_places=3,
    )

    # What the quantity is counted or measured in ("kg", "bags"), if given.
    unit: str | None = Field(
        default=None,
        max_length=20,
    )

    # The line's total (e.g. 2 pizzas -> the price of both), before discount.
    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    # The price of one unit, when known. With it, quantity x unit price is
    # the line's total (to the paisa per unit, as bills round).
    unit_price: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    # Whose it is (their parts add up to the price). Empty: not said.
    owners: list[ExpenseItemOwnerCreate] = Field(
        default_factory=list,
        max_length=50,
    )

    @model_validator(mode="after")
    def owners_add_up(self) -> "ExpenseItemCreate":
        if self.owners:
            owned = sum((owner.amount for owner in self.owners), Decimal("0"))
            if owned != self.amount:
                raise ValueError(
                    f"The owners of {self.name} add up to {owned}, but it cost {self.amount}."
                )
            check_no_repeats([owner.counterparty_id for owner in self.owners], "owner")
        return self

    @model_validator(mode="after")
    def unit_price_fits(self) -> "ExpenseItemCreate":
        # Quantity x unit price is the line's total, within a paisa per unit.
        if self.unit_price is not None and abs(self.unit_price * self.quantity - self.amount) > (
            Decimal("0.01") * max(self.quantity, Decimal("1"))
        ):
            raise ValueError(
                f"{self.quantity:g} x {self.unit_price} for {self.name} isn't its price {self.amount}."
            )
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = clean_optional_text(value)

        if name is None:
            raise ValueError("Item name cannot be empty.")

        return name

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        unit = clean_optional_text(value)

        return unit.lower() if unit else None


class ExpenseChargeCreate(BaseModel):
    """
    Something the bill added on top of the items: tax, service charge,
    delivery, a tip, a fee. Not an item: nothing was bought.
    """

    kind: ChargeKind

    # As the bill names it ("CGST 9%"). Left out: the kind's usual name.
    label: str | None = Field(
        default=None,
        max_length=100,
    )

    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    @model_validator(mode="after")
    def default_label(self) -> "ExpenseChargeCreate":
        self.label = clean_optional_text(self.label) or CHARGE_LABELS[self.kind]
        return self


class ExpenseDeductionCreate(BaseModel):
    """
    Something taken off the bill: a discount, a refund for part of it,
    rounding down. Each kind stays its own line.
    """

    kind: DeductionKind

    # As the bill names it ("Coupon SAVE50"). Left out: the kind's usual name.
    label: str | None = Field(
        default=None,
        max_length=100,
    )

    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    @model_validator(mode="after")
    def default_label(self) -> "ExpenseDeductionCreate":
        self.label = clean_optional_text(self.label) or DEDUCTION_LABELS[self.kind]
        return self


class ExpenseRefundCreate(BaseModel):
    """
    Money given back after paying (e.g. a returned item). counterparty_id
    is who got it; null means you. Never a discount or a payment.
    """

    counterparty_id: int | None = None

    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    # What it was for ("Returned one shirt"). Optional.
    label: str | None = Field(
        default=None,
        max_length=100,
    )

    # When the money came back. Left out: the expense's date.
    date: dt.date | None = None

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ExpenseParticipantCreate(BaseModel):
    """Someone who shares the cost, and their share. Null means you."""

    counterparty_id: int | None = None

    share_amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )


def check_no_repeats(people: list[int | None], what: str) -> None:
    """
    Explanation:
        Refuse a list that names the same person twice (you count as the
        person None).

    Parameters:
        people: The counterparty ids in the list, None for you.
        what: "payer" or "person", for the message.

    Raises:
        ValueError: If someone appears more than once.
    """
    if len(set(people)) != len(people):
        raise ValueError(f"The same {what} appears more than once.")


def check_adds_up(amounts: list[Decimal], total: Decimal, what: str) -> None:
    """
    Explanation:
        Refuse amounts that don't add up exactly to the expense amount,
        because balances would then be wrong.

    Parameters:
        amounts: The payments or shares.
        total: The expense amount.
        what: "Payments" or "Shares", for the message.

    Raises:
        ValueError: If the sum differs from the total.
    """
    added = sum(amounts, Decimal("0"))

    if added != total:
        raise ValueError(f"{what} add up to {added} but the expense is {total}.")


# Used for both creating and fully replacing (editing) an expense
class ExpenseCreate(BaseModel):
    date: dt.date

    # Up to 10 digits before the point and 2 after, like the database column.
    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    # Left out: the user's default currency is used.
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    description: str | None = Field(
        default=None,
        max_length=255,
    )

    category: Category = DEFAULT_CATEGORY

    # Anything worth keeping about it ("an estimate", "repeats every
    # month"). Optional.
    note: str | None = Field(
        default=None,
        max_length=500,
    )

    # Who the money went to ("Swiggy"): one of your contacts. Optional.
    counterparty_id: int | None = None

    # Who paid. Left out: you paid the whole amount.
    payments: list[ExpensePaymentCreate] | None = Field(
        default=None,
        min_length=1,
    )

    # Whose cost it was. Left out: it was all yours.
    participants: list[ExpenseParticipantCreate] | None = Field(
        default=None,
        min_length=1,
    )

    # What was taken off the bill, line by line (discounts, refunds,
    # rounding down). `amount` is what was charged after them.
    deductions: list[ExpenseDeductionCreate] = Field(
        default_factory=list,
        max_length=50,
    )

    # The total taken off. Worked out from `deductions` when they're given
    # (a different total is refused); a total with no lines is one discount.
    discount_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    # What was bought, line by line. Optional.
    items: list[ExpenseItemCreate] = Field(
        default_factory=list,
        max_length=200,
    )

    # What the bill added on top of the items (tax, fees, tips). Optional.
    charges: list[ExpenseChargeCreate] = Field(
        default_factory=list,
        max_length=50,
    )

    # Money given back after paying, each to one person. Shares add up to
    # the amount less these (the cost that was really shared).
    refunds: list[ExpenseRefundCreate] = Field(
        default_factory=list,
        max_length=50,
    )

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        # Store currency codes uppercase and letters-only.
        if value is None:
            return None

        return clean_currency_code(value)

    @model_validator(mode="after")
    def check_payments_and_shares(self) -> "ExpenseCreate":
        """
        Explanation:
            When payments or shares are given, they must add up exactly to
            the amount, and nobody may have two shares. (A payer may appear
            twice: part by card, part in cash.)

            The bill itself: items - discount + charges = amount. So when
            items are given, that must hold exactly; without items the
            charges must still leave something that was bought.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If a rule is broken.
        """
        if self.payments is not None:
            check_adds_up([p.amount for p in self.payments], self.amount, "Payments")

        # Every deduction is kept as a line of its own kind, and the total
        # is only ever their sum.
        if self.deductions:
            deducted = sum((d.amount for d in self.deductions), Decimal("0"))
            if self.discount_amount and self.discount_amount != deducted:
                raise ValueError(
                    f"Deductions add up to {deducted} but the total taken off is "
                    f"{self.discount_amount}."
                )
            self.discount_amount = deducted
        elif self.discount_amount:
            self.deductions = [
                ExpenseDeductionCreate(kind="discount", amount=self.discount_amount)
            ]

        charge_total = sum((charge.amount for charge in self.charges), Decimal("0"))

        if self.items:
            item_total = sum((item.amount for item in self.items), Decimal("0"))
            charged = item_total - self.discount_amount + charge_total

            if charged != self.amount:
                steps = f"Items add up to {item_total}"
                if self.discount_amount:
                    steps += f", less the {self.discount_amount} discount"
                if charge_total:
                    steps += f", plus {charge_total} in charges"
                if self.discount_amount or charge_total:
                    steps += f", that's {charged},"
                raise ValueError(f"{steps} but the expense is {self.amount}.")

        elif charge_total >= self.amount + self.discount_amount:
            raise ValueError(
                f"Charges add up to {charge_total}, which leaves nothing for what was bought "
                f"in an expense of {self.amount}."
            )

        # A refund gives back part of what was paid, to someone who paid.
        refunded = sum((refund.amount for refund in self.refunds), Decimal("0"))
        if self.refunds:
            if refunded >= self.amount:
                raise ValueError(
                    f"Refunds add up to {refunded}, which is all of the expense ({self.amount}) or more."
                )
            paid: dict[int | None, Decimal] = {}
            for payment in self.payments or [ExpensePaymentCreate(amount=self.amount)]:
                paid[payment.counterparty_id] = paid.get(payment.counterparty_id, Decimal("0")) + payment.amount
            if any(refund.counterparty_id not in paid for refund in self.refunds):
                raise ValueError("A refund goes back to someone who paid.")
            back: dict[int | None, Decimal] = {}
            for refund in self.refunds:
                back[refund.counterparty_id] = back.get(refund.counterparty_id, Decimal("0")) + refund.amount
            if any(amount > paid[person] for person, amount in back.items()):
                raise ValueError("Someone got more back than they paid.")

        if self.participants is not None:
            check_no_repeats([p.counterparty_id for p in self.participants], "person")
            check_adds_up(
                [p.share_amount for p in self.participants],
                self.amount - refunded,
                "Shares" if not self.refunds else "Shares (after refunds)",
            )

        # Whose an item is and who shares the cost must agree: an item's
        # owner has a share (unless a refund gave all of it back).
        sharers = {p.counterparty_id for p in self.participants} if self.participants is not None else {None}
        if not self.refunds and any(
            owner.counterparty_id not in sharers for item in self.items for owner in item.owners
        ):
            raise ValueError("Someone an item belongs to has no share of the cost.")

        return self

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """
        Explanation:
            Trim the description and collapse repeated spaces; an empty
            one is stored as no description at all.

        Parameters:
            value: The description as sent.

        Returns:
            The cleaned description, or None.
        """
        if value is None:
            return None

        description = " ".join(value.split())

        return description or None

class ExpensePaymentResponse(BaseModel):
    # A payment as the API returns it. counterparty_id null means you.

    counterparty_id: int | None
    amount: Decimal
    method: str | None
    provider: str | None

    model_config = ConfigDict(
        from_attributes=True,
    )

class ExpenseItemOwnerResponse(BaseModel):
    """An item's owner as the API returns it. counterparty_id null means you."""

    counterparty_id: int | None
    amount: Decimal

    model_config = ConfigDict(
        from_attributes=True,
    )

class ExpenseItemResponse(BaseModel):
    """One bill line as the API returns it."""

    name: str
    quantity: Decimal
    unit: str | None
    amount: Decimal
    unit_price: Decimal | None = None
    owners: list[ExpenseItemOwnerResponse] = Field(default_factory=list)

    model_config = ConfigDict(
        from_attributes=True,
    )

class ExpenseChargeResponse(BaseModel):
    """A charge (tax, fee, tip...) as the API returns it."""

    kind: str
    label: str
    amount: Decimal

    model_config = ConfigDict(
        from_attributes=True,
    )

class ExpenseDeductionResponse(BaseModel):
    """A deduction (discount, refund, rounding) as the API returns it."""

    kind: str
    label: str
    amount: Decimal

    model_config = ConfigDict(
        from_attributes=True,
    )

class ExpenseRefundResponse(BaseModel):
    """A refund as the API returns it. counterparty_id null means you."""

    counterparty_id: int | None
    amount: Decimal
    label: str | None
    date: dt.date

    model_config = ConfigDict(
        from_attributes=True,
    )

class ExpenseParticipantResponse(BaseModel):
    """A share as the API returns it. counterparty_id null means you."""

    counterparty_id: int | None
    share_amount: Decimal

    model_config = ConfigDict(
        from_attributes=True,
    )

class ExpenseResponse(BaseModel):
    # An expense as the API returns it. Amounts are sent as strings
    id: int
    date: dt.date
    amount: Decimal                 # what was charged, after deductions
    discount_amount: Decimal        # the deductions' total
    original_amount: Decimal        # before deductions: amount + discount_amount
                                    # (items + charges, when items are listed)
    currency: str
    description: str | None
    category: str
    counterparty_id: int | None
    payments: list[ExpensePaymentResponse]
    participants: list[ExpenseParticipantResponse]
    items: list[ExpenseItemResponse]
    charges: list[ExpenseChargeResponse]
    deductions: list[ExpenseDeductionResponse]
    refunds: list[ExpenseRefundResponse]
    note: str | None = None
    # Repayments saved as settling this expense (see Settlement.expense_id).
    settlement_ids: list[int] = Field(default_factory=list)
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(
        from_attributes=True,
    )

class CategoryOption(BaseModel):
    # One category: the key the API uses and the label the UI shows.
    key: str
    label: str


# COUNTERPARTIES (CONTACTS)
CounterpartyType = Literal["PERSON", "BUSINESS", "ORGANIZATION"]

def clean_contact_name(value: str | None) -> str:
    """
    Explanation:
        Trim a contact name and collapse repeated spaces. A missing or
        blank name is refused: every contact needs one.

    Parameters:
        value: The name as sent.

    Returns:
        The cleaned name.

    Raises:
        ValueError: If the name is missing or blank.
    """
    name = " ".join((value or "").split())

    if not name:
        raise ValueError("Name cannot be empty.")

    return name


def clean_relation(value: str | None) -> str | None:
    """
    Explanation:
        Store a relation lowercase with single spaces ("My  Wife" ->
        "my wife"), so it matches the user's own words later. Blank means
        no relation.

    Parameters:
        value: The relation as sent, or None.

    Returns:
        The cleaned relation, or None.
    """
    if value is None:
        return None

    relation = " ".join(value.lower().split())

    return relation or None


def upper_type(value: object) -> object:
    """Accept the type in any case ("person" -> "PERSON") before it's checked."""
    if isinstance(value, str):
        return value.strip().upper()

    return value


class CounterpartyCreate(BaseModel):
    # A new contact: a person, business or organization.

    name: str = Field(
        max_length=255,
    )

    counterparty_type: CounterpartyType = "PERSON"

    relation: str | None = Field(
        default=None,
        max_length=50,
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return clean_contact_name(value)

    @field_validator("counterparty_type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> object:
        return upper_type(value)

    @field_validator("relation")
    @classmethod
    def normalize_relation(cls, value: str | None) -> str | None:
        return clean_relation(value)


class CounterpartyUpdate(BaseModel):
    """
    Change a contact. Only the fields actually sent are changed, so a
    rename keeps the type and relation. Sending "relation": null clears it.
    """

    name: str | None = Field(
        default=None,
        max_length=255,
    )

    counterparty_type: CounterpartyType | None = None

    relation: str | None = Field(
        default=None,
        max_length=50,
    )

    # Validators only run on values that were sent, so leaving name out is
    # fine, but sending "name": null is refused.
    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str:
        return clean_contact_name(value)

    @field_validator("counterparty_type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> object:
        if value is None:
            raise ValueError("Type cannot be empty.")

        return upper_type(value)

    @field_validator("relation")
    @classmethod
    def normalize_relation(cls, value: str | None) -> str | None:
        return clean_relation(value)


class CounterpartyResponse(BaseModel):
    """A contact as the API returns it."""

    id: int
    name: str
    counterparty_type: str
    relation: str | None

    model_config = ConfigDict(
        from_attributes=True,
    )

# BALANCES AND SETTLEMENTS
SettlementDirection = Literal["they_paid_me", "i_paid_them"]

# What money between you and a contact was (see models.Settlement).
SettlementKind = Literal["repayment", "loan", "reimbursement", "gift", "balance"]


class MergeContacts(BaseModel):
    # Merge a contact into this one (the same person under two names).
    into_id: int


class ExpenseToSettlement(BaseModel):
    # An expense that was really money between you and a contact.
    counterparty_id: int
    direction: Literal["they_paid_me", "i_paid_them"]
    kind: SettlementKind = "repayment"

class SettlementCreate(BaseModel):
    # Money between you and a contact: which way it went, and what it was.

    counterparty_id: int

    direction: SettlementDirection

    kind: SettlementKind = "repayment"

    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    # Left out: your default currency.
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    date: dt.date

    note: str | None = Field(
        default=None,
        max_length=255,
    )

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return clean_currency_code(value)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return " ".join(value.split()) or None


class SettlementResponse(BaseModel):
    # A settlement as the API returns it.

    id: int
    counterparty_id: int
    direction: str
    kind: str = "repayment"
    amount: Decimal
    currency: str
    date: dt.date
    note: str | None
    # The expense it settles, when saved with one.
    expense_id: int | None = None

    model_config = ConfigDict(
        from_attributes=True,
    )


# Money expected between the user and a contact that hasn't moved yet
# ("Parth will pay me back 500 next week"). Changes no balance until it
# happens, when it becomes a settlement.
ExpectedDirection = Literal["they_pay_me", "i_pay_them"]


class ExpectedResponse(BaseModel):
    id: int
    counterparty_id: int
    direction: str
    kind: str
    amount: Decimal | None
    currency: str
    due_date: dt.date | None
    note: str | None
    created_at: dt.datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class ExpectedDone(BaseModel):
    # It happened: for how much (left out: as expected) and when.
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    date: dt.date


class Balance(BaseModel):
    """
    What one contact and you owe each other in one currency.
    Positive amount: they owe you. Negative: you owe them.
    """
    counterparty_id: int
    name: str
    currency: str
    amount: Decimal

# MONTHLY SUMMARY
class CategoryTotal(BaseModel):
    category: str
    amount: Decimal


class CurrencySummary(BaseModel):
    # One month's totals in one currency (currencies are never mixed).

    currency: str
    your_spending: Decimal # your shares of this month's expenses
    you_paid: Decimal # money you paid out for this month's expenses
    expense_count: int
    by_category: list[CategoryTotal] # your spending, biggest first
    owed_to_you: Decimal # all-time, from balances
    you_owe: Decimal # all-time, from balances


class MonthSummary(BaseModel):
    month: str # "YYYY-MM"
    currencies: list[CurrencySummary]

# ASSISTANT (natural-language entry)
#
# The assistant turns text into drafts. A draft is shown to the user and
# only saved when they confirm it. People in a draft are you, one of your
# contacts, or a new contact the assistant proposes (created on confirm).
class DraftPerson(BaseModel):
    # You, one of your contacts, or a proposed new contact (by new_key)
    kind: Literal["me", "contact", "new"]
    contact_id: int | None = None
    new_key: str | None = None
    name: str

class DraftNewContact(BaseModel):
    # A contact the assistant proposes to create when the draft is saved.

    key: str = Field(
        max_length=20,
    )

    name: str = Field(
        max_length=255,
    )

    counterparty_type: CounterpartyType = "PERSON"

    relation: str | None = Field(
        default=None,
        max_length=50,
    )

    # The user said this is someone new (a person or organization is never
    # created without that; a shop that was paid is).
    confirmed: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return clean_contact_name(value)

    @field_validator("relation")
    @classmethod
    def normalize_relation(cls, value: str | None) -> str | None:
        return clean_relation(value)

class DraftPayment(BaseModel):
    person: DraftPerson
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: PaymentMethod | None = None
    provider: str | None = Field(default=None, max_length=100)

class DraftShare(BaseModel):
    person: DraftPerson
    share_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

class DraftRefund(BaseModel):
    # Money given back after paying, and who got it.
    person: DraftPerson
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    label: str | None = Field(default=None, max_length=100)
    date: dt.date

# Answers to a draft's question that the server applies exactly, whatever
# words the user would have used:
#   keep_total / keep_parts    a stated total and the bill's parts disagree
#   refund_owner:<n>           refund n comes off only its recipient's share
#   refund_shared:<n>          refund n comes off everyone's, in proportion
#   shares_from_repayment /    the shares stated and a repayment in the same
#   shares_as_stated           message disagree: which is right
#   new_person:<name>          a name not in People is someone new
#   money_kind:<n>:<kind>      what money n between people was (repayment...)
#   owner:me / owner:equal /   whose a cost nothing allocated is: the user's,
#   owner:<name>               shared equally by everyone in it, or one person's
#   estimates_ok               amounts the user said were rough are kept as they are
#   pay_later                  what the user still has to pay counts as paid by them
#   record_once                a repeating cost: record one payment of it
#   extra_debt                 a debt is on top of what the records already show
#   not_duplicate              it isn't the same as one already saved
#   same_person:<name>         a longer name is the contact with its first name
#   split_with:<name|everyone> who an even split nobody was named for is with
#   my_share_only              a group not named: record only the user's share
#   owe_payer / treat          someone else paid the user's own cost: owed, or their treat
#   price_final / price_before one price and a discount or tax: the price is what was
#                              paid, or before the change
DECISIONS = (
    "keep_total", "keep_parts", "shares_from_repayment", "shares_as_stated",
    "estimates_ok", "pay_later", "record_once", "extra_debt", "not_duplicate",
    "my_share_only", "owe_payer", "treat", "price_final", "price_before",
)


def check_decision(value: str) -> str:
    kind, _, index = value.partition(":")
    if value in DECISIONS or (
        kind in ("refund_owner", "refund_shared") and index.isdigit()
    ) or (kind in ("new_person", "same_person", "owner", "rest", "split_with") and index.strip()) or (
        kind == "money_kind"
        and index.partition(":")[0].isdigit()
        and index.partition(":")[2] in ("repayment", "loan", "reimbursement", "gift", "balance")
    ) or (
        kind in ("settle_currency", "add_shop")
        and index.partition(":")[0].isdigit()
        and index.partition(":")[2].strip() != ""
    ):
        return value
    raise ValueError(f"{value!r} isn't an answer this draft offers.")

class DraftChoice(BaseModel):
    decision: str
    label: str  # e.g. "The total 1,600.00 is right"

class ExpenseDraft(BaseModel):
    """
    One expense as the assistant understood it. problems lists what it
    couldn't work out or check; a draft with problems can't be saved as
    is (the user rephrases or enters it by hand).
    """
    excerpt: str
    date: dt.date
    amount: Decimal | None
    currency: str
    description: str | None
    category: str
    discount_amount: Decimal  # the deductions' total
    items: list[ExpenseItemCreate]
    charges: list[ExpenseChargeCreate] = Field(default_factory=list)
    deductions: list[ExpenseDeductionCreate] = Field(default_factory=list)
    # Money given back after paying; shares add up to amount less these.
    refunds: list[DraftRefund] = Field(default_factory=list)
    # One per item: whose it is and how much ([] when not said).
    item_owners: list[list[DraftShare]] = Field(default_factory=list)
    paid_to: DraftPerson | None
    payments: list[DraftPayment]
    participants: list[DraftShare]
    new_contacts: list[DraftNewContact]
    problems: list[str]
    # What was worked out and should be visible, e.g. change given back.
    notes: list[str] = Field(default_factory=list)
    # One-tap answers to its problems, when there are exact ones.
    choices: list[DraftChoice] = Field(default_factory=list)

class AssistantPreviewRequest(BaseModel):
    # What the user typed, e.g. "Lunch 350 with Parth, split equally".

    text: str = Field(
        max_length=2000,
    )

    # The user's own date, so "yesterday" is theirs, not the server's.
    today: dt.date | None = None

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        text = value.strip()

        if not text:
            raise ValueError("Describe an expense first.")

        return text

class ClarificationTurn(BaseModel):
    # One round of questions about a draft, and what the user answered.

    asked: list[str] = Field(
        max_length=20,
    )

    answer: str = Field(
        max_length=1000,
    )

    @field_validator("asked")
    @classmethod
    def short_questions(cls, value: list[str]) -> list[str]:
        if any(len(question) > 500 for question in value):
            raise ValueError("A question is too long.")

        return value

    @field_validator("answer")
    @classmethod
    def answered(cls, value: str) -> str:
        answer = value.strip()

        if not answer:
            raise ValueError("Write an answer first.")

        return answer

class AssistantClarifyRequest(BaseModel):
    # A draft's description again, with the answers to its questions so far.

    text: str = Field(
        max_length=2000,
    )

    turns: list[ClarificationTurn] = Field(
        min_length=1,
        max_length=30,
    )

    # Choices picked on the draft so far; they still apply after the
    # description is read again.
    decisions: list[str] = Field(
        default_factory=list,
        max_length=50,
    )

    # With several things in one message, the one asked about (its
    # excerpt): the whole message is read again, for context, and only
    # what this part describes comes back.
    focus: str | None = Field(
        default=None,
        max_length=2000,
    )

    today: dt.date | None = None

    @field_validator("decisions")
    @classmethod
    def known_decisions(cls, value: list[str]) -> list[str]:
        return [check_decision(decision) for decision in value]

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        text = value.strip()

        if not text:
            raise ValueError("Describe an expense first.")

        return text

class RepaymentDraft(BaseModel):
    """
    Money paid back between you and one person, as the assistant
    understood it. Saved as a settlement, never as an expense.
    """

    excerpt: str
    date: dt.date
    amount: Decimal | None
    currency: str
    method: PaymentMethod | None
    # What it was: repayment, loan, reimbursement or gift (None: not said,
    # and asked).
    kind: SettlementKind | None = "repayment"
    from_person: DraftPerson
    to_person: DraftPerson
    new_contacts: list[DraftNewContact]
    problems: list[str]
    # Things worked out that the user should see (saved with it).
    notes: list[str] = Field(default_factory=list)
    # Exact answers the user can pick for its questions.
    choices: list[DraftChoice] = Field(default_factory=list)
    # The excerpt of the expense in the same message it settles, if any,
    # so the two are saved linked.
    settles_excerpt: str | None = None


class ExpectedDraft(BaseModel):
    """
    Money between the user and someone that hasn't moved yet ("he'll
    return the 500 next week"): nothing changes until it happens, but it
    can be remembered.
    """

    excerpt: str
    from_person: DraftPerson
    to_person: DraftPerson
    amount: Decimal | None
    currency: str
    kind: SettlementKind = "repayment"
    due_date: dt.date | None = None
    new_contacts: list[DraftNewContact] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    choices: list[DraftChoice] = Field(default_factory=list)


class ExpectedConfirm(BaseModel):
    """An expected-money draft the user wants remembered."""

    from_person: DraftPerson
    to_person: DraftPerson
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: str | None = None
    kind: SettlementKind = "repayment"
    due_date: dt.date | None = None
    note: str | None = Field(default=None, max_length=255)
    new_contacts: list[DraftNewContact] = Field(default_factory=list)


class AssistantPreviewResponse(BaseModel):
    expenses: list[ExpenseDraft]
    repayments: list[RepaymentDraft] = Field(default_factory=list)
    # Money that hasn't moved yet, which can be remembered.
    expected: list[ExpectedDraft] = Field(default_factory=list)
    # Parts of the message that can't be recorded here, with why.
    skipped: list[str] = Field(default_factory=list)


class RepaymentConfirm(BaseModel):
    """A repayment draft the user accepted, sent back to be saved."""

    date: dt.date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str | None = None
    method: PaymentMethod | None = None
    kind: SettlementKind = "repayment"
    from_person: DraftPerson
    to_person: DraftPerson
    new_contacts: list[DraftNewContact] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # The saved expense it settles (from the same message), if any.
    expense_id: int | None = None

class DraftConfirm(BaseModel):
    # A draft the user accepted, sent back to be saved exactly as shown.

    date: dt.date
    amount: Decimal
    currency: str | None = None
    description: str | None = None
    category: Category = DEFAULT_CATEGORY
    discount_amount: Decimal = Decimal("0")
    items: list[ExpenseItemCreate] = Field(default_factory=list)
    charges: list[ExpenseChargeCreate] = Field(default_factory=list)
    deductions: list[ExpenseDeductionCreate] = Field(default_factory=list)
    refunds: list[DraftRefund] = Field(default_factory=list)
    item_owners: list[list[DraftShare]] = Field(default_factory=list)
    paid_to: DraftPerson | None = None
    payments: list[DraftPayment] = Field(min_length=1)
    participants: list[DraftShare] = Field(min_length=1)
    new_contacts: list[DraftNewContact] = Field(default_factory=list)
    # What was worked out, kept with the expense.
    notes: list[str] = Field(default_factory=list)
    # Repayments from the same message already saved, which settle it.
    settlement_ids: list[int] = Field(default_factory=list)
