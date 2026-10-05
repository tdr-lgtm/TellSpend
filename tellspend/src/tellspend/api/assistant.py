import datetime as dt
import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from tellspend.api.auth import get_current_user
from tellspend.api.schemas import (
    AssistantClarifyRequest,
    AssistantPreviewRequest,
    AssistantPreviewResponse,
    DraftChoice,
    DraftConfirm,
    DraftNewContact,
    DraftPerson,
    ExpectedConfirm,
    ExpectedResponse,
    ExpenseCreate,
    ExpenseResponse,
    RepaymentConfirm,
    SettlementCreate,
    SettlementResponse,
)
from tellspend.database.connection import get_db
from tellspend.database.models import Counterparty, ExpectedMoney, Expense, Settlement, User
from tellspend.ingestion.builder import build_result
from tellspend.ingestion.extractor import AssistantUnavailable, extract
from tellspend.services.balances import compute_balances
from tellspend.services.expense_writer import write_expense
from tellspend.services.ownership import get_owned_counterparty, get_owned_expense
from tellspend.services.rate_limit import check_assistant_limit

router = APIRouter(
    prefix="/assistant",
    tags=["assistant"],
)

def read_text(
    text: str,
    user: User,
    db: Session,
    turns: list[tuple[list[str], str]] | None = None,
    decisions: set[str] | None = None,
    today: dt.date | None = None,
    focus: str | None = None,
) -> AssistantPreviewResponse:
    """
    Explanation:
        Read a description (with any answers to questions about it) and
        build a draft for every expense and repayment in it. Answers are
        held to the same rules as the description: every number must be
        in what the user actually typed, the description or an answer.

    Parameters:
        text: The description the user typed.
        user: The signed-in user.
        db: The database session for this request.
        turns: Questions asked about the text and the user's answers,
            oldest first.
        decisions: Choices the user picked on the draft ("keep_total"...).
        today: The user's own date, used when it's within a day of the
            server's (time zones differ by less than that).
        focus: The excerpt of the one part asked about, when the message
            describes several: only what's about it comes back.

    Returns:
        The drafts (each with any problems) and skipped parts.

    Raises:
        HTTPException 503 if the assistant isn't set up or unavailable;
        429 when the user has asked too often.
    """
    turns = turns or []
    server_today = dt.date.today()
    today = today if today is not None and abs((today - server_today).days) <= 1 else server_today

    check_assistant_limit(user.id)

    try:
        extracted = extract(text, today, user.name, turns=turns)
    except AssistantUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error.user_message,
        )

    contacts = list(
        db.scalars(select(Counterparty).where(Counterparty.owner_user_id == user.id))
    )

    # For "settled everything" repayments: current balances in the
    # user's currency (positive: they owe the user).
    # contact id -> currency -> balance (positive: they owe the user).
    balances: dict[int, dict[str, Decimal]] = {}
    for balance in compute_balances(db, user):
        balances.setdefault(balance.counterparty_id, {})[balance.currency] = balance.amount

    # Everything the user typed, where evidence may come from.
    typed = "\n".join([text, *(answer for _, answer in turns)])

    result = build_result(extracted, typed, user, contacts, today, balances, decisions)
    if focus:
        result = only_about(result, focus)
    if "not_duplicate" not in (decisions or set()):
        flag_duplicates(result, user, db)
    return result


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def is_about(excerpt: str, focus: str) -> bool:
    """True if most of the shorter of the two is in the other (same words, any order)."""
    a, b = _words(excerpt), _words(focus)
    return bool(a and b) and len(a & b) / min(len(a), len(b)) >= 0.5


def only_about(result: AssistantPreviewResponse, focus: str) -> AssistantPreviewResponse:
    """
    What a message read again whole says about one of its parts: the
    other parts are on their own cards already. If nothing matches (the
    answer changed it beyond recognition), everything comes back, so
    nothing is lost.
    """
    def quoted(message: str) -> str:
        found = re.search(r"“(.*?)”", message)
        return found.group(1) if found else message

    focused = result.model_copy(update={
        "expenses": [d for d in result.expenses if is_about(d.excerpt, focus)],
        "repayments": [d for d in result.repayments if is_about(d.excerpt, focus)],
        "expected": [d for d in result.expected if is_about(d.excerpt, focus)],
        "skipped": [m for m in result.skipped if is_about(quoted(m), focus)],
    })
    if focused.expenses or focused.repayments or focused.expected or focused.skipped:
        return focused
    return result


def settlement_direction(from_person: DraftPerson, to_person: DraftPerson, kind: str | None) -> str:
    """
    How money between the user and someone is stored: who handed it over,
    or for an existing debt (from who owes to who is owed), as if the one
    owed had handed it over (see models.Settlement).
    """
    they_paid_me = to_person.kind == "me"
    if kind == "balance":
        they_paid_me = not they_paid_me
    return "they_paid_me" if they_paid_me else "i_paid_them"


def flag_duplicates(result: AssistantPreviewResponse, user: User, db: Session) -> None:
    """
    Explanation:
        A draft just like something already saved (same date, amount,
        currency and description; for money between people, the same
        person, kind and way) may be the same event told again. Saving it would count it
        twice, so it's asked, with a one-tap "it's a new one".

    Parameters:
        result: The drafts, changed in place.
        user: The signed-in user.
        db: The database session for this request.
    """
    def ask(draft, what: str) -> None:
        draft.problems.append(f"You already saved {what}. Is this the same one? If so, there's nothing to save.")
        draft.choices.append(DraftChoice(decision="not_duplicate", label="No, it's a new one"))

    for draft in result.expenses:
        if draft.amount is None:
            continue
        same_day = db.scalars(
            select(Expense).where(
                Expense.user_id == user.id, Expense.date == draft.date,
                Expense.amount == draft.amount, Expense.currency == draft.currency,
            )
        ).all()
        # Two different things can cost the same on one day; the same
        # description too is what makes it look told twice.
        saved = next((e for e in same_day if _words(e.description or "") == _words(draft.description or "")), None)
        if saved is not None:
            ask(draft, f"“{saved.description or 'an expense'}” for {saved.currency} {saved.amount:,.2f} "
                       f"on {saved.date:%d %b %Y}")

    for repayment in result.repayments:
        other = repayment.to_person if repayment.from_person.kind == "me" else repayment.from_person
        if repayment.amount is None or repayment.kind is None or other.contact_id is None:
            continue
        saved = db.scalars(
            select(Settlement).where(
                Settlement.user_id == user.id, Settlement.counterparty_id == other.contact_id,
                Settlement.date == repayment.date, Settlement.amount == repayment.amount,
                Settlement.currency == repayment.currency, Settlement.kind == repayment.kind,
                Settlement.direction == settlement_direction(
                    repayment.from_person, repayment.to_person, repayment.kind),
            )
        ).first()
        if saved is not None:
            ask(repayment, f"this with {other.name} ({saved.currency} {saved.amount:,.2f} on {saved.date:%d %b %Y})")


@router.post("/preview", response_model=AssistantPreviewResponse)
def preview(
    request: AssistantPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Read the user's description and return a draft for every expense
        and repayment in it, plus what couldn't be recorded. Nothing is
        saved.

    Parameters:
        request: The text the user typed.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The drafts (each with any problems) and skipped parts.

    Raises:
        HTTPException 503 if the assistant isn't set up or unavailable.
    """
    return read_text(request.text, current_user, db, today=request.today)


@router.post("/clarify", response_model=AssistantPreviewResponse)
def clarify(
    request: AssistantClarifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Answer a draft's questions: read its description again together
        with every answer so far, and return the drafts it now describes,
        which replace the one asked about. Nothing is saved.

    Parameters:
        request: The draft's description and each round of questions and answers.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The drafts (each with any problems still left) and skipped parts.

    Raises:
        HTTPException 503 if the assistant isn't set up or unavailable.
    """
    turns = [(turn.asked, turn.answer) for turn in request.turns]
    return read_text(request.text, current_user, db, turns, set(request.decisions),
                     today=request.today, focus=request.focus)


class DraftPeople:
    """
    Turns draft people into contact ids for saving, creating each proposed
    new contact once (in the caller's transaction).
    """

    def __init__(self, db: Session, user: User, new_contacts: list[DraftNewContact]):
        self.db = db
        self.user = user
        self.proposed = {contact.key: contact for contact in new_contacts}
        self.created: dict[str, int] = {}

    def contact_id(self, person: DraftPerson) -> int | None:
        """The counterparty id for a draft person (None for the user)."""
        if person.kind == "me":
            return None

        if person.kind == "contact":
            if person.contact_id is None:
                raise HTTPException(status_code=422, detail="A contact in the draft has no id.")
            return person.contact_id

        if person.new_key not in self.proposed:
            raise HTTPException(
                status_code=422, detail=f"{person.name} isn't in the draft's new contacts."
            )

        if person.new_key not in self.created:
            new = self.proposed[person.new_key]

            # The same name, whatever its case or spacing, is the same
            # contact: reuse it rather than creating a second one.
            key = " ".join(new.name.casefold().split())
            existing = next(
                (c for c in self.db.scalars(select(Counterparty).where(Counterparty.owner_user_id == self.user.id))
                 if " ".join(c.name.casefold().split()) == key),
                None,
            )
            if existing is not None:
                self.created[person.new_key] = existing.id
                return existing.id

            # A person or organization is only created when the user said
            # they're someone new.
            if new.counterparty_type != "BUSINESS" and not new.confirmed:
                raise HTTPException(
                    status_code=422,
                    detail=f"{new.name} isn't in your People. Confirm they're someone new first.",
                )

            contact = Counterparty(
                owner_user_id=self.user.id,
                name=new.name,
                counterparty_type=new.counterparty_type,
                relation=new.relation,
            )
            self.db.add(contact)
            self.db.flush()
            self.created[person.new_key] = contact.id

        return self.created[person.new_key]


@router.post(
    "/confirm-repayment",
    response_model=SettlementResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_repayment(
    draft: RepaymentConfirm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Save an accepted repayment as a settlement (creating the contact it
        proposes, if any), in one transaction. Exactly one side must be the
        user; the other side is the settlement's contact.

    Parameters:
        draft: The accepted repayment draft.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The saved settlement (201); 422 if it isn't between the user and
        one other person; 404 for someone else's contact.
    """
    if (draft.from_person.kind == "me") == (draft.to_person.kind == "me"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A repayment must be between you and one other person.",
        )

    people = DraftPeople(db, current_user, draft.new_contacts)
    they_paid_me = draft.to_person.kind == "me"
    other = draft.from_person if they_paid_me else draft.to_person
    direction = settlement_direction(draft.from_person, draft.to_person, draft.kind)

    try:
        counterparty_id = people.contact_id(other)
        get_owned_counterparty(db, current_user, counterparty_id)
        if draft.expense_id is not None:
            get_owned_expense(db, current_user, draft.expense_id)
        data = SettlementCreate(
            counterparty_id=counterparty_id,
            direction=direction,
            kind=draft.kind,
            amount=draft.amount,
            currency=draft.currency,
            date=draft.date,
            # How it was paid and what was worked out (e.g. paid in another
            # currency), so nothing the message said is lost.
            note=" ".join(
                [f"By {draft.method.replace('_', ' ')}." if draft.method else "", *draft.notes]
            ).strip()[:255] or None,
        )
    except HTTPException:
        db.rollback()
        raise
    except ValidationError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {"loc": ["body", *item["loc"]], "msg": item["msg"], "type": item["type"]}
                for item in error.errors()
            ],
        )

    settlement = Settlement(
        user_id=current_user.id,
        counterparty_id=data.counterparty_id,
        direction=data.direction,
        kind=data.kind,
        amount=data.amount,
        currency=data.currency or current_user.default_currency,
        date=data.date,
        note=data.note,
        expense_id=draft.expense_id,
    )
    db.add(settlement)
    db.commit()
    db.refresh(settlement)

    return settlement


@router.post(
    "/confirm-expected",
    response_model=ExpectedResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_expected(
    draft: ExpectedConfirm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Remember money that hasn't moved yet ("Parth will pay me back 500
        next week"), creating the contact it proposes. It changes no
        balance until it's marked as happened (see api/expected.py).

    Parameters:
        draft: The expected-money draft.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The remembered money (201); 422 if it isn't between the user and
        one other person.
    """
    if (draft.from_person.kind == "me") == (draft.to_person.kind == "me"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This must be between you and one other person.",
        )

    they_pay_me = draft.to_person.kind == "me"
    other = draft.from_person if they_pay_me else draft.to_person
    try:
        counterparty_id = DraftPeople(db, current_user, draft.new_contacts).contact_id(other)
        get_owned_counterparty(db, current_user, counterparty_id)
    except HTTPException:
        db.rollback()
        raise

    expected = ExpectedMoney(
        user_id=current_user.id,
        counterparty_id=counterparty_id,
        direction="they_pay_me" if they_pay_me else "i_pay_them",
        kind=draft.kind if draft.kind != "balance" else "repayment",
        amount=draft.amount,
        currency=(draft.currency or current_user.default_currency).upper(),
        due_date=draft.due_date,
        note=" ".join((draft.note or "").split())[:255] or None,
    )
    db.add(expected)
    db.commit()
    db.refresh(expected)
    return expected


@router.post(
    "/confirm",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm(
    draft: DraftConfirm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Save a draft the user accepted: create the new contacts it
        proposes, then the expense, in ONE transaction. If anything is
        wrong, nothing is saved (no stray contacts).

    Parameters:
        draft: The accepted draft.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The saved expense (201); 422 if its amounts don't add up, 404 if
        it names someone else's contact.
    """
    contact_id = DraftPeople(db, current_user, draft.new_contacts).contact_id

    try:
        expense_data = ExpenseCreate(
            date=draft.date,
            amount=draft.amount,
            currency=draft.currency,
            description=draft.description,
            category=draft.category,
            note=" ".join(draft.notes)[:500] or None,
            discount_amount=draft.discount_amount,
            items=[
                {
                    **item.model_dump(exclude={"owners"}),
                    "owners": [
                        {"counterparty_id": contact_id(owner.person), "amount": owner.share_amount}
                        for owner in (draft.item_owners[index] if index < len(draft.item_owners) else [])
                    ],
                }
                for index, item in enumerate(draft.items)
            ],
            charges=draft.charges,
            deductions=draft.deductions,
            refunds=[
                {
                    "counterparty_id": contact_id(refund.person),
                    "amount": refund.amount,
                    "label": refund.label,
                    "date": refund.date,
                }
                for refund in draft.refunds
            ],
            counterparty_id=contact_id(draft.paid_to) if draft.paid_to else None,
            payments=[
                {
                    "counterparty_id": contact_id(payment.person),
                    "amount": payment.amount,
                    "method": payment.method,
                    "provider": payment.provider,
                }
                for payment in draft.payments
            ],
            participants=[
                {"counterparty_id": contact_id(share.person), "share_amount": share.share_amount}
                for share in draft.participants
            ],
        )
    except ValidationError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {"loc": ["body", *item["loc"]], "msg": item["msg"], "type": item["type"]}
                for item in error.errors()
            ],
        )
    except HTTPException:
        db.rollback()
        raise

    try:
        expense = write_expense(db, current_user, expense_data)
    except HTTPException:
        # E.g. someone else's contact: drop the contacts created above too.
        db.rollback()
        raise

    # Repayments from the same message, saved first, that settle it.
    if draft.settlement_ids:
        for settlement in db.scalars(
            select(Settlement).where(
                Settlement.id.in_(draft.settlement_ids), Settlement.user_id == current_user.id
            )
        ):
            settlement.expense_id = expense.id

    db.commit()
    db.refresh(expense)

    return expense