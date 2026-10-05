"""
Extraction -> draft: the deterministic half of the assistant.

The model only reports what the user said. This module decides what it
means, the same way every time:

- Every number must be backed by its evidence, and the evidence must be
  in the user's text. Anything else was invented and is refused.
- People are matched to the user's contacts: by full name, by first name
  when that's unique, or by relationship ("my wife"). Unknown names
  become proposed new contacts; ambiguous ones become problems.
- All arithmetic happens here: the total from the items, "the rest" of a
  payment or share, and equal splits (exact to the paisa).
- Who pays for what comes from everything the message establishes,
  backed by the user's words (one phrase or several) like any number.
  Items said to be someone's are theirs; what isn't anyone's own is
  shared by the people the split names, else the people the expense is
  for. A split that names nobody but the user is shared by the people in
  the expense (with a note); stated shares that leave part of the total
  to nobody leave it to the one person in the expense they don't list;
  a repayment in the same message that settles what its payer owed makes
  their share what they paid plus what they paid back. With nobody else
  involved, it's the user's.

Only what can't be worked out from all of that is asked, in `problems`,
never guessed; a draft with problems can't be saved.
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from itertools import combinations
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pydantic import ValidationError

from tellspend.api.schemas import (
    AssistantPreviewResponse,
    DraftNewContact,
    DraftPayment,
    DraftChoice,
    DraftPerson,
    DraftRefund,
    DraftShare,
    ExpenseChargeCreate,
    ExpenseDeductionCreate,
    ExpenseDraft,
    ExpenseItemCreate,
    ExpectedDraft,
    RepaymentDraft,
)
from tellspend.categories import CATEGORY_KEYS, DEFAULT_CATEGORY
from tellspend.charges import CHARGE_KINDS, CHARGE_LABELS
from tellspend.deductions import DEDUCTION_KINDS, DEDUCTION_LABELS
from tellspend.database.models import Counterparty, User
from tellspend.ingestion.extraction import (
    SELF_REF,
    Adjustment,
    Entity,
    ExpenseExtraction,
    ExtractedExpenses,
    ExtractedItem,
    ExtractedPayment,
    ExtractedRefund,
    ExtractedRepayment,
    ExtractedShare,
    ExtractedSplit,
    Money,
    NotRecorded,
)
from tellspend.services.balances import net_with_you
from tellspend.services.money import PAISA, allocate


ME = DraftPerson(kind="me", name="You")

ZERO = Decimal("0")

def fits_effect(adjustment: Adjustment) -> bool:
    """
    True if the adjustment's kind can do what it's said to do: a charge
    kind adds to the bill, a deduction kind takes money off. A kind that
    contradicts its effect (a "discount" that adds) is never re-labelled
    as something else.
    """
    kinds = CHARGE_KINDS if adjustment.effect == "adds" else DEDUCTION_KINDS
    return adjustment.kind in kinds


def adjustment_label(adjustment: Adjustment) -> str:
    """Its name as the user wrote it, else a plain name for its kind."""
    label = " ".join((adjustment.label or "").split())[:100]
    labels = CHARGE_LABELS if adjustment.effect == "adds" else DEDUCTION_LABELS
    return label or labels.get(adjustment.kind, "Adjustment")


def as_charge(adjustment: Adjustment, amount: Decimal) -> ExpenseChargeCreate:
    """An adjustment that adds to the bill, stored as a charge of its own kind."""
    return ExpenseChargeCreate(kind=adjustment.kind, label=adjustment_label(adjustment), amount=amount)


def as_deduction(adjustment: Adjustment, amount: Decimal) -> ExpenseDeductionCreate:
    """An adjustment that takes money off, stored as a deduction of its own kind."""
    return ExpenseDeductionCreate(
        kind=adjustment.kind, label=adjustment_label(adjustment), amount=amount
    )


# When the stated total and the bill's parts disagree, what the user can
# tell us is right. Offered as choices on the draft and applied here, so a
# confirmation never depends on how it was worded.
DIFFERENCE_LABEL = "Difference from the total"


@dataclass
class Line:
    """
    One adjustment on a bill, as the split needs it: what it is, and what
    it was worked out on, so it can be shared the same way.

        stage 1  deductions, on the items
        stage 2  charges, on the items after deductions
        stage 3  taxes, on that plus the taxable charges
        stage 4  worked out from the total afterwards (e.g. a difference)
    """

    label: str
    amount: Decimal  # always positive; `adds` says which way
    adds: bool
    stage: int
    taxable: bool = False  # a charge that taxes are worked out on
    owners: list[str] = field(default_factory=list)  # said to be these people's
    items: list[str] = field(default_factory=list)  # said to apply to these lines


@dataclass
class Bill:
    """A bill worked out from its parts (see Builder.build_bill)."""

    items: list[ExpenseItemCreate]  # only what was bought
    deductions: list[ExpenseDeductionCreate]  # each thing taken off, by kind
    charges: list[ExpenseChargeCreate]  # everything added: tax, fees, tips...
    final: Decimal | None  # None when the parts aren't complete
    breakdown: str | None  # "Items 1,550.00 - Discount 100.00 + Tax 130.00 = 1,580.00"
    # The price before adjustments is known (every item priced, or a
    # subtotal given), so the parts can be checked against a total.
    has_base: bool = False
    base: Decimal = Decimal("0")
    # Adjustments mentioned without an amount but said to be inside the
    # total ("1,100 including tax"); worked out from the total later.
    included: list[Adjustment] = field(default_factory=list)
    # Each priced part: its name, price and who the user said it was for
    # (refs; [] = nobody named).
    owned: list[tuple[str, Decimal, list[str]]] = field(default_factory=list)
    # The one item with no price, to be priced from the total.
    missing: ExtractedItem | None = None
    missing_quantity: Decimal = Decimal("1")
    # For each entry of `owned`, the bill line (item name) it's part of,
    # and that item's index in `items` (None for a price with no item).
    part_lines: list[str] = field(default_factory=list)
    part_items: list[int | None] = field(default_factory=list)
    # Every deduction and charge, in the order they apply, for the split.
    lines: list[Line] = field(default_factory=list)

    @property
    def deducted(self) -> Decimal:
        """Everything taken off, in total."""
        return sum((d.amount for d in self.deductions), ZERO)

    @property
    def charged(self) -> Decimal:
        """Everything added, in total."""
        return sum((c.amount for c in self.charges), ZERO)

    @property
    def parts(self) -> Decimal:
        """What the parts come to: the price before adjustments - deductions + charges."""
        return self.base - self.deducted + self.charged

TYPE_FOR_KIND = {
    "person": "PERSON",
    "business": "BUSINESS",
    "organization": "ORGANIZATION",
}

# The first number written in some evidence ("1,200", "99.50"), and the
# word right after it, if any ("1.2k", "2 lakh").
NUMBER_PATTERN = re.compile(r"(\d[\d,]*(?:\.\d+)?)(\s*[^\W\d_]+)?")


def _normalize(text: str) -> str:
    # Lowercase with single spaces, for "is this phrase in the text" checks.
    return " ".join(text.casefold().split())

def positive(text: str | None) -> Decimal:
    """A stated quantity as a number; 1 when it's missing or not a positive number."""
    try:
        number = Decimal(text or "1")
    except InvalidOperation:
        return Decimal("1")
    return number if number.is_finite() and number > 0 else Decimal("1")


def is_power_of_ten(ratio: Decimal) -> bool:
    """True for 100, 1000, 100000...: what a scale word can multiply by."""
    if ratio != ratio.to_integral_value() or ratio < 100:
        return False
    digits = str(int(ratio))
    return digits == "1" + "0" * (len(digits) - 1)


def evidence_supports(value: Decimal, evidence: str) -> bool | None:
    """
    Explanation:
        Whether the evidence says this number. Its digits must be the
        number itself, or, when a word follows them, the number scaled by
        a power of ten of at least 100: that's what scale words do in any
        language ("1.2k", "2 lakh", "3 million"), so no list of them is
        needed.

    Parameters:
        value: The number the model read.
        evidence: The words the model says it came from.

    Returns:
        True or False; None if the evidence has no digits ("five hundred").
    """
    match = NUMBER_PATTERN.search(evidence)

    if match is None:
        return None

    number = Decimal(match.group(1).replace(",", ""))

    if value == number:
        return True

    return bool(match.group(2)) and number > 0 and is_power_of_ten(value / number)

@dataclass
class Builder:
    # Builds one draft; collects problems and proposed contacts as it goes.
    text: str
    user: User
    contacts: list[Counterparty]
    today: dt.date
    # For repayments of "their share": each person's share of the expenses
    # in the same message (by identity()).
    shares_in_message: dict[tuple, Decimal] = field(default_factory=dict)
    # Repayments in the same message that settle what their payer owed for
    # this expense: (payer, receiver) by identity() -> the amount.
    settled: dict[tuple, Money] = field(default_factory=dict)
    # The words stating each repayment's money in this message (normalized).
    repaid_words: set[str] = field(default_factory=set)
    # Who the user pays back (or says they will) in this message, by
    # identity(): someone who paid for the user is then owed it.
    repaid_to: set[tuple] = field(default_factory=set)
    # Something the user stated about whose it is (an owner, a split, who
    # it's for) couldn't be checked: then no default fills its place.
    allocation_refused: bool = False
    # For "settled everything": contact id -> balance in the user's
    # currency (positive: they owe the user).
    # contact id -> currency -> balance (positive: they owe the user).
    balances: dict[int, dict[str, Decimal]] = field(default_factory=dict)
    # What this message's expenses leave owed: identity() -> currency ->
    # amount (positive: they owe the user). Added to the saved balances.
    message_balances: dict[tuple, dict[str, Decimal]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    # Things worked out that the user should see, e.g. change given back.
    notes: list[str] = field(default_factory=list)
    # Answers the user picked from a draft's choices ("keep_total"...),
    # applied exactly, and the choices this draft offers.
    decisions: set[str] = field(default_factory=set)
    choices: list[DraftChoice] = field(default_factory=list)
    new_contacts: list[DraftNewContact] = field(default_factory=list)
    # Keys of new contacts an answer, in the user's own words, said are
    # someone new: the same as picking "Yes, add them".
    said_new: set[str] = field(default_factory=set)
    people: dict[str, DraftPerson | None] = field(default_factory=dict)
    # Refs of shops and brands (and whoever was paid): they can be paid,
    # but never have a share of the cost.
    businesses: set[str] = field(default_factory=set)
    # Refs of organizations (an employer, a client): a cost can be theirs
    # when the message says so, but being mentioned doesn't involve them.
    organizations: set[str] = field(default_factory=set)
    # Refs of every person involved other than the user, in any role. With
    # nobody else involved, whatever isn't anyone's own can only be the
    # user's; otherwise whose it is must be said.
    others: set[str] = field(default_factory=set)
    # Who shares what isn't anyone's own, once the split is worked out.
    sharers: list[str] = field(default_factory=lambda: [SELF_REF])
    # Whether the split says who shares each item that isn't anyone's own
    # (an even split or a split by items does; stated amounts don't).
    items_follow_split: bool = False
    # The message says this is the user's own household's cost, with
    # everyone else in it from that household (the model's reading, its
    # words checked). Nobody owes anyone for it.
    household: bool = False
    # Refs of who paid, as stated (empty when nobody said).
    payer_refs: list[str] = field(default_factory=list)
    # How to speak of someone known only by how they relate to the user:
    # ref -> "your wife" (their contact name would just be "Wife").
    called: dict[str, str] = field(default_factory=dict)
    # New contact key -> the note saying what they'll be saved as, shown
    # only if the draft adds them.
    saved_as: dict[str, str] = field(default_factory=dict)

    # numbers
    def money(self, money: Money | None, what: str) -> Decimal | None:
        """
        Explanation:
            Accept a number only if its evidence is in the user's text and
            says the same number. Anything else is reported, not used.

        Parameters:
            money: The number and its evidence, or None if not stated.
            what: What the number is, for the problem message.

        Returns:
            The amount with 2 decimals, or None.
        """
        if money is None:
            return None

        try:
            value = Decimal(money.value.replace(",", "").strip())
        except InvalidOperation:
            self.problems.append(f"I couldn't read the {what} ({money.value!r}).")
            return None

        in_text = _normalize(money.evidence) in _normalize(self.text)

        if not in_text or evidence_supports(value, money.evidence) is False:
            self.problems.append(f"I couldn't find the {what} ({value}) in what you wrote.")
            return None

        if value <= 0 or value != value.quantize(Decimal("0.01")):
            self.problems.append(f"The {what} ({value}) isn't a valid amount.")
            return None

        value = value.quantize(Decimal("0.01"))

        # A rough number is never saved as if it were exact: it's asked,
        # and kept as it is only when the user says it's close enough.
        if money.approximate:
            if "estimates_ok" in self.decisions:
                self.notes.append(f"The {what} {value:,.2f} is an estimate (you said “{money.evidence.strip()}”).")
            else:
                self.problems.append(
                    f"You said “{money.evidence.strip()}” for the {what}. What was the exact amount?"
                )
                if not any(choice.decision == "estimates_ok" for choice in self.choices):
                    self.choices.append(DraftChoice(decision="estimates_ok", label="Save the estimate as it is"))

        return value

    def stated(self, evidence: str | list[str] | None) -> bool:
        """
        True if the words the model quoted are in the user's text. A fact
        the message establishes in several places is quoted as several
        phrases; each must be there.
        """
        phrases = [evidence] if isinstance(evidence, str) else list(evidence or [])
        text = _normalize(self.text)
        words = [_normalize(phrase) for phrase in phrases if _normalize(phrase)]
        return bool(words) and all(phrase in text for phrase in words)

    def owners_of(self, item: ExtractedItem) -> list[str]:
        """Who a whole item was said to be for (see owners)."""
        return self.owners(item.for_refs, item.for_evidence, f"the {item.name}")

    def owners(self, for_refs: list[str], evidence: str | None, what: str) -> list[str]:
        """
        Explanation:
            Who something was said to be for. Like a number, this is only
            accepted when the words saying it are in the user's text.

        Parameters:
            for_refs: The refs the model says it's for.
            evidence: The words the model says state it.
            what: What it is ("the pasta"), for messages.

        Returns:
            The refs it's for ([] = nobody named), or [] with a problem
            recorded when the model couldn't back it up.
        """
        refs = list(dict.fromkeys(for_refs))

        if refs and not self.stated(evidence):
            self.problems.append(f"I couldn't find where you said who {what} was for.")
            self.allocation_refused = True
            return []

        if not self.only_people(refs):
            return []

        self.note_even(refs, what)
        return refs

    def scope_of(
        self,
        thing: Adjustment | ExtractedRefund,
        label: str,
        line_names: list[str],
    ) -> tuple[list[str], list[str]] | None:
        """
        Explanation:
            Who an adjustment or refund was said to be for, and which of
            the bill's lines it applies to. Like everything else, only
            accepted when the words saying it are in the user's text.

        Parameters:
            thing: The adjustment or refund (for_refs, items, applies_evidence).
            label: What it is, for messages ("the delivery").
            line_names: The names of the bill's items.

        Returns:
            (owners' refs, names of the lines it applies to); both empty
            for the whole bill. None with a problem recorded when it can't
            be backed up or the items aren't on the bill.
        """
        if not thing.for_refs and not thing.items:
            return [], []

        # A charge, discount or refund on every item on the bill is on the
        # whole bill: nothing to back up (a refund then follows the usual
        # rule: one sharer's, else asked). A tax on the items is different:
        # it says the charges aren't taxed, so its words are checked.
        every_item = {_normalize(name) for name in line_names}
        if (
            not thing.for_refs
            and getattr(thing, "kind", None) != "tax"
            and every_item
            and {_normalize(name) for name in thing.items} == every_item
        ):
            return [], []

        if not self.stated(thing.applies_evidence):
            self.problems.append(f"I couldn't find where you said who or what {label} was for.")
            return None

        owners = self.owners(thing.for_refs, thing.applies_evidence, label)

        names = []
        for wanted in dict.fromkeys(thing.items):
            found = [name for name in line_names if _normalize(name) == _normalize(wanted)]
            if not found:
                self.problems.append(f"{label.capitalize()} is for the {wanted}, but I couldn't find it on the bill.")
                return None
            names.append(found[0])

        return owners, names

    def who(self, refs: list[str]) -> str:
        """The people refs name, for notes: "you", "Parth and Riya", "nobody named"."""
        names = []
        for ref in refs:
            person = self.people.get(ref)
            if person is not None:
                names.append("you" if person.kind == "me" else person.name)
        if not names:
            return "nobody named"
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"

    def whose(self, refs: list[str]) -> str:
        """The people refs name, possessive, for notes: "your", "Parth's", "Parth's and Riya's"."""
        names = []
        for ref in refs:
            person = self.people.get(ref)
            if person is not None:
                names.append("your" if person.kind == "me" else f"{person.name}'s")
        if not names:
            return "nobody's"
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"

    def portions_of(
        self,
        item: ExtractedItem,
        line_total: Decimal | None,
        quantity: Decimal,
    ) -> tuple[Decimal, list[tuple[str, Decimal, list[str]]], list[Decimal | None]] | None:
        """
        Explanation:
            Who each part of one bill line is for, and what each part
            costs. Only what the numbers already given determine is worked
            out, the same rule as "the rest" of a payment:

                every part priced          the line is their sum; if they
                                           come to less and don't account
                                           for every unit, the rest of the
                                           line is unclaimed
                one part without a price   it's what the line leaves
                several without a price    units on one line share its unit
                                           price, unless the user priced
                                           them differently (then asked)

            A part with no count is one unit when units are needed to
            work something out. Units no part claims are the line's rest,
            for whoever the whole line is for (else nobody named).

        Parameters:
            item: The extracted line.
            line_total: Its price, if known (stated, or unit price x quantity).
            quantity: How many units it has.

        Returns:
            (the line's price, [(name, price, refs) for each part], each
            part's number of units or None when not known), or None with a
            problem recorded.
        """
        if not item.portions:
            if line_total is None:
                return None
            return line_total, [(item.name, line_total, self.owners_of(item))], [quantity]

        rest_name = f"rest of the {item.name}"

        # [name, refs, units counted in the text or None, price or None]
        parts: list[list] = []
        for portion in item.portions:
            refs = self.owners(portion.for_refs, portion.for_evidence, f"part of the {item.name}")
            price = self.money(portion.amount, f"price of {self.who(refs)}'s {item.name}")
            if portion.amount is not None and price is None:
                return None
            counted = positive(portion.quantity) if portion.quantity is not None else None
            parts.append([item.name, refs, counted, price])

        counted_total = sum((part[2] for part in parts if part[2] is not None), ZERO)
        if counted_total > quantity:
            self.problems.append(
                f"The parts of the {item.name} come to {counted_total:g}, but there were {quantity:g}."
            )
            return None

        known = sum((part[3] for part in parts if part[3] is not None), ZERO)
        unknown = [part for part in parts if part[3] is None]

        if line_total is None:
            if unknown:
                self.problems.append(f"What did the {item.name} cost?")
                return None
            line_total = known

        mismatch = (
            f"The parts of the {item.name} come to {known:,.2f}, but you said "
            f"{line_total:,.2f} for it."
        )

        if not unknown:
            every_unit = all(part[2] is not None for part in parts) and counted_total == quantity
            if known > line_total or (known < line_total and every_unit):
                self.problems.append(mismatch)
                return None
            if known < line_total:
                # What no part claims is the rest of the line.
                parts.append([rest_name, self.owners_of(item), None, line_total - known])

        else:
            # Units are needed now: a part with no count is one unit, and
            # units no part claims are the rest of the line.
            units = [part[2] if part[2] is not None else Decimal("1") for part in parts]
            used = sum(units, ZERO)

            # More uncounted, unpriced parts than there are units: they're
            # people sharing what's left of the line, evenly, the same rule
            # as an item for several people.
            if used > quantity and all(part[2] is None for part in unknown):
                sharers = [ref for part in unknown for ref in part[1]]
                for part, price in zip(unknown, allocate(line_total - known, [Decimal(1)] * len(unknown))):
                    part[3] = price
                self.note_even(list(dict.fromkeys(sharers)), f"the {item.name}")
                return line_total, [(name, price, refs) for name, refs, _, price in parts], [None] * len(parts)

            if used > quantity:
                self.problems.append(
                    f"The parts of the {item.name} come to {used:g}, but there were {quantity:g}."
                )
                return None
            if used < quantity:
                rest = [rest_name, self.owners_of(item), quantity - used, None]
                parts.append(rest)
                unknown.append(rest)
                units.append(quantity - used)
            for part, count in zip(parts, units):
                part[2] = count

            if len(unknown) == 1:
                left = line_total - known
                if left <= 0:
                    self.problems.append(
                        f"The priced parts of the {item.name} already come to {known:,.2f} of "
                        f"{line_total:,.2f}. What did the rest cost?"
                    )
                    return None
                unknown[0][3] = left
                if known:
                    self.notes.append(
                        f"{self.whose(unknown[0][1]).capitalize()} part of the {item.name} is what "
                        f"the {line_total:,.2f} leaves: {left:,.2f}."
                    )
            else:
                # Several parts without a price: only units on one line
                # priced alike can say what each costs. A part priced
                # otherwise means they weren't, and the rest isn't known.
                unit_of = {id(part): count for part, count in zip(parts, units)}
                alike = all(
                    part[3] * quantity == line_total * unit_of[id(part)]
                    for part in parts
                    if part[3] is not None
                )
                if not alike:
                    self.problems.append(f"What did each of the other {item.name} cost?")
                    return None
                weights = [unit_of[id(part)] for part in unknown]
                for part, price in zip(unknown, allocate(line_total - known, weights)):
                    part[3] = price
                each = (line_total / quantity).quantize(PAISA, ROUND_HALF_UP)
                self.notes.append(f"Every unit on the {item.name} line is priced alike: {each:,.2f} each.")

        return line_total, [(name, price, refs) for name, refs, _, price in parts], [part[2] for part in parts]

    def only_people(self, refs: list[str]) -> bool:
        """
        True if every ref can have a share of the cost. A shop, or whoever
        was paid, never owes a share of it: that's a problem. People can,
        and so can an organization (an employer, a client) when the message
        says the cost is theirs.
        """
        if any(ref in self.businesses for ref in refs):
            self.problems.append(
                "A shop or business can't have a share of the cost. Say which people it's for."
            )
            return False
        return True

    def people_in_expense(self) -> list[str]:
        """The user and every other person in this expense, in order (never a business)."""
        return [SELF_REF, *(ref for ref in self.people if ref in self.others)]

    def note_even(self, refs: list[str], what: str) -> None:
        """
        Something for several people with no amounts given is split
        evenly between them; say so, so it's never a silent choice.
        """
        if len(refs) < 2:
            return
        people = [self.people.get(ref) for ref in refs]
        names = [
            "you" if person.kind == "me" else self.called.get(ref, person.name)
            for ref, person in zip(refs, people) if person is not None
        ]
        if len(names) == len(refs):
            listed = ", ".join(names[:-1]) + f" and {names[-1]}"
            self.notes.append(f"No amounts were given for {what}, so it's split evenly between {listed}.")

    # people
    def match_contact(self, entity: Entity) -> Counterparty | str | None:
        """
        Explanation:
            Find the contact an entity refers to. Tries, in order: the full
            name, the first name (when only one contact has it), then the
            relationship. Case and extra spaces never matter.

        Parameters:
            entity: A person or business from the extraction.

        Returns:
            The contact, "ambiguous" if several fit, or None if none do.
        """
        candidates: list[list[Counterparty]] = []
        # Only a full name is enough on its own; a first name or a
        # relationship only fits a contact of the same kind (a shop
        # "Zara" is never the person "Zara Khan").
        alike = [c for c in self.contacts if same_kind(entity, c)]

        if entity.name:
            name = _normalize(entity.name)
            candidates.append([c for c in self.contacts if _normalize(c.name) == name])
            candidates.append(
                [c for c in alike if _normalize(c.name).split(" ")[0] == name]
            )

        if entity.relationship:
            relation = _normalize(entity.relationship)
            candidates.append(
                [c for c in alike if c.relation and _normalize(c.relation) == relation]
            )

        for matches in candidates:
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return "ambiguous"

        return None

    def resolve_entities(self, entities: list[Entity], used: set[str] | None = None) -> None:
        """
        Explanation:
            Decide who every entity is: you, an existing contact, or a new
            contact to create. Fills self.people (ref -> person, or None
            when it couldn't be decided, with a problem recorded).

        Parameters:
            entities: The extraction's entities.
        """
        self.people[SELF_REF] = ME
        self.businesses = {e.ref for e in entities if e.kind == "business"}
        self.organizations = {e.ref for e in entities if e.kind == "organization"}
        self.others = {
            e.ref for e in entities if e.kind == "person" and e.ref != SELF_REF
        }

        for entity in entities:
            if entity.ref == SELF_REF or entity.kind == "self":
                self.people[entity.ref] = ME
                continue

            label = entity.name or f"your {entity.relationship or 'contact'}"
            match = self.match_contact(entity)

            if isinstance(match, Counterparty):
                self.people[entity.ref] = DraftPerson(
                    kind="contact", contact_id=match.id, name=match.name
                )
                if match.relation and _normalize(match.name) == _normalize(match.relation):
                    self.called[entity.ref] = f"your {_normalize(match.relation)}"
            elif match == "ambiguous":
                self.problems.append(
                    f"More than one of your contacts could be {label}. "
                    "Use their full name, or enter this one by hand."
                )
                self.people[entity.ref] = None
            elif (
                (used is None or entity.ref in used)
                and (maybe := self.maybe_contact(entity)) is not None
                and not self.is_new(entity)
            ):
                # "Parth Shah" when People has one "Parth": the same
                # person is likely but not certain, so it's asked.
                if f"same_person:{_normalize(entity.name)}" in self.decisions:
                    self.people[entity.ref] = DraftPerson(kind="contact", contact_id=maybe.id, name=maybe.name)
                else:
                    self.problems.append(f"Is {entity.name.strip()} your contact {maybe.name}?")
                    for decision, label in (
                        (f"same_person:{_normalize(entity.name)}", f"Yes, it's {maybe.name}"),
                        (f"new_person:{_normalize(entity.name)}", "No, someone new"),
                    ):
                        if all(choice.decision != decision for choice in self.choices):
                            self.choices.append(DraftChoice(decision=decision, label=label))
                    self.people[entity.ref] = None
            elif entity.name or entity.relationship:
                # Someone new. Named only by how they relate to the user
                # ("my sister"): proposed under that, which they can rename
                # later; two new "friends" become "Friend" and "Friend 2".
                name = entity.name or self.unused_name(entity.relationship.strip().capitalize())
                key = f"new{len(self.new_contacts) + 1}"
                if not entity.name:
                    self.called[entity.ref] = label
                    self.saved_as[key] = f"{label.capitalize()} isn't in your people yet; saving adds them as “{name}”."
                try:
                    contact = DraftNewContact(
                        key=key,
                        name=name,
                        counterparty_type=TYPE_FOR_KIND.get(entity.kind, "PERSON"),
                        relation=entity.relationship if entity.kind == "person" else None,
                    )
                except ValidationError:
                    self.problems.append(f"{name!r} isn't a usable contact name.")
                    self.people[entity.ref] = None
                    continue

                self.new_contacts.append(contact)
                if self.stated(entity.said_new):
                    self.said_new.add(key)
                self.people[entity.ref] = DraftPerson(kind="new", new_key=key, name=contact.name)
            elif used is not None and entity.ref not in used:
                # Nothing in this expense refers to them: nothing to ask.
                self.people[entity.ref] = None
            elif entity.kind == "person":
                self.problems.append(
                    "Someone in this isn't named. Say who they are, or enter it by hand."
                )
                self.people[entity.ref] = None
            else:
                what = "shop or business" if entity.kind == "business" else "organization"
                self.problems.append(f"Which {what} was it? Say its name, or enter it by hand.")
                self.people[entity.ref] = None

    def maybe_contact(self, entity: Entity) -> Counterparty | None:
        """
        The one contact of the same kind whose whole name is the first
        word of a longer name ("Parth" for "Parth Shah"), else None.
        """
        words = _normalize(entity.name or "").split(" ")
        if len(words) < 2:
            return None
        found = [c for c in self.contacts if same_kind(entity, c) and _normalize(c.name) == words[0]]
        return found[0] if len(found) == 1 else None

    def is_new(self, entity: Entity) -> bool:
        """True once the user said this name is someone new (a choice or their own words)."""
        return f"new_person:{_normalize(entity.name or '')}" in self.decisions or self.stated(entity.said_new)

    def confirm_new_people(self, used: set[str]) -> None:
        """
        A person or organization the draft uses that isn't in People is
        asked about, never created on its own: "yes, someone new" is a
        choice; an answer naming someone in People replaces them.
        """
        for contact in self.new_contacts:
            if contact.key in used and contact.key in self.saved_as:
                self.notes.append(self.saved_as[contact.key])
            if contact.key not in used or contact.counterparty_type == "BUSINESS":
                continue
            decision = f"new_person:{_normalize(contact.name)}"
            if decision in self.decisions or contact.key in self.said_new:
                contact.confirmed = True
                continue
            # Known only by how they relate to the user ("your wife"): that
            # says who they are, so it's only whether to add them.
            called = next((self.called[ref] for ref, person in self.people.items()
                           if ref in self.called and person is not None and person.new_key == contact.key), None)
            if called is not None:
                self.problems.append(f"{called.capitalize()} isn't in your People yet. Add them?")
                self.choices.append(DraftChoice(decision=decision, label=f"Yes, add {called}"))
                continue
            self.problems.append(f"{contact.name} isn't in your People. Is {contact.name} someone new?")
            self.choices.append(DraftChoice(decision=decision, label=f"Yes, add {contact.name}"))

    def unused_name(self, base: str) -> str:
        """base, or "base 2", "base 3"... so no two contacts share a name."""
        taken = {_normalize(c.name) for c in self.contacts}
        taken.update(_normalize(c.name) for c in self.new_contacts)

        name, number = base, 1
        while _normalize(name) in taken:
            number += 1
            name = f"{base} {number}"

        return name

    def person(self, ref: str | None) -> DraftPerson | None:
        # The person for a ref; an unknown ref (a model mistake) is a problem.
        if ref is None:
            return None

        if ref not in self.people:
            self.problems.append("I got confused about who was involved. Please rephrase.")
            self.people[ref] = None

        return self.people[ref]

    # ---------- the bill: items and adjustments ----------

    def percent(self, money: Money, what: str) -> Decimal | None:
        """
        Explanation:
            Accept a percentage only if its evidence is in the user's text,
            says the same number, and it's between 0 and 100.

        Parameters:
            money: The percentage and its evidence ("18", "18%").
            what: What it's a percentage of, for the problem message.

        Returns:
            The percentage, or None (with a problem recorded).
        """
        try:
            value = Decimal(money.value.replace("%", "").strip())
        except InvalidOperation:
            self.problems.append(f"I couldn't read the {what} percentage ({money.value!r}).")
            return None

        in_text = _normalize(money.evidence) in _normalize(self.text)
        match = NUMBER_PATTERN.search(money.evidence)

        # A percentage is never scaled: its digits must be the number.
        if not in_text or (match and Decimal(match.group(1).replace(",", "")) != value):
            self.problems.append(f"I couldn't find the {what} ({value}%) in what you wrote.")
            return None

        if not ZERO < value <= 100:
            self.problems.append(f"The {what} ({value}%) isn't a valid percentage.")
            return None

        return value

    def build_bill(
        self, extraction: ExpenseExtraction, total_stated: bool, derived: dict[int, Decimal] | None = None,
    ) -> Bill:
        """
        Explanation:
            Work out the bill from its parts, the same way for every kind
            of bill:

                final = items + everything that adds - everything that subtracts

            Items: a stated line price, or unit price x quantity (or one
            subtotal when no items are listed).
            Adjustments (taxes, fees, tips, delivery, service charges,
            discounts, rounding...) are money amounts or percentages,
            applied in the order a real bill uses:
                1. discounts, as a percentage of the items
                2. charges (service, delivery, packaging, fees, tips), as a
                   percentage of the items after discounts
                3. taxes, as a percentage of all that except tips

            To store it the parts stay apart: items are only what was
            bought, subtractions become the discount and additions become
            charges, so items - discount + charges = final. A subtotal
            with no item list isn't an item (nothing was named); it is only
            the base the adjustments apply to.

        Parameters:
            extraction: What the model extracted.
            total_stated: Whether the user stated a final total (then
                percentages with no items to apply to are only shown).
            derived: Prices worked out for items with none stated, by
                their index in the extraction's items (price_from_total).

        Returns:
            The bill: its items, discount, charges, final amount (None if
            it can't be worked out from the parts) and a breakdown for the
            user.
        """
        items: list[ExpenseItemCreate] = []
        # Each priced part of each line: (name, price, refs it's for), and
        # the line each is part of.
        owned: list[tuple[str, Decimal, list[str]]] = []
        part_lines: list[str] = []
        part_items: list[int | None] = []
        complete = True
        unpriced: list[tuple[ExtractedItem, Decimal]] = []

        for index, extracted in enumerate(extraction.items):
            quantity = positive(extracted.quantity)

            line_total = self.money(extracted.line_total, f"price of {extracted.name}")
            stated_price = extracted.line_total is not None
            if line_total is None and not stated_price and not extracted.unit_price and derived and index in derived:
                line_total = derived[index]

            stated_unit = (
                self.money(extracted.unit_price, f"price of one {extracted.name}")
                if extracted.unit_price else None
            )
            if line_total is None and not stated_price and extracted.unit_price:
                stated_price = True
                if stated_unit is not None:
                    line_total = (stated_unit * quantity).quantize(PAISA, ROUND_HALF_UP)

            # A stated price that failed its check stops here; with no
            # price stated at all, the parts may still say it.
            if line_total is None and stated_price:
                complete = False
                continue

            before = len(self.problems)
            priced = self.portions_of(extracted, line_total, quantity)

            if priced is None:
                if not extracted.portions or len(self.problems) == before:
                    # Maybe the total says it ("the rest was my paratha");
                    # decided at the end, when the other unknowns are known.
                    unpriced.append((extracted, quantity))
                complete = False
                continue

            line_total, parts, counts = priced

            # Parts of a line that are different people's, with known units
            # ("3 shirts: one mine, one hers, one shared"), stay separate
            # items: each with its units, price and owners. Otherwise the
            # line is one item, its parts only in who owns how much of it.
            separate = (
                len(parts) > 1
                and None not in counts
                and sum(counts, ZERO) == quantity
                and all(price > 0 for _, price, _ in parts)
            )
            lines = (
                [(price, count) for (_, price, _), count in zip(parts, counts)]
                if separate else [(line_total, quantity)]
            )

            try:
                first = len(items)
                for price, count in lines:
                    items.append(
                        ExpenseItemCreate(
                            name=extracted.name,
                            quantity=count,
                            unit=extracted.unit,
                            amount=price,
                            unit_price=unit_price_of(price, count, stated_unit, whole=not separate),
                        )
                    )
                owned.extend(parts)
                part_lines.extend([extracted.name] * len(parts))
                part_items.extend(
                    [first + index for index in range(len(parts))] if separate else [first] * len(parts)
                )
            except ValidationError:
                del items[first:]
                self.problems.append(f"I couldn't read the item {extracted.name!r}.")
                complete = False

        # A price given as one amount instead of an item list ("dinner
        # 3,200 plus 5% GST") is the base; it isn't stored as an item.
        stated_subtotal = self.money(extraction.subtotal, "price before charges")
        subtotal = sum((item.amount for item in items), ZERO)

        if extraction.subtotal is not None and stated_subtotal is None:
            complete = False
        elif stated_subtotal is not None and not extraction.items:
            subtotal = stated_subtotal
            name = " ".join((extraction.description or "").split()) or "the bill"
            owned = [(name, stated_subtotal, [])]
            part_lines = [name]
            part_items = [None]

        # Both items and a subtotal: they must agree.
        if stated_subtotal is not None and extraction.items and complete and subtotal != stated_subtotal:
            self.problems.append(
                f"The items come to {subtotal:,.2f}, but the price you gave is "
                f"{stated_subtotal:,.2f}."
            )
            complete = False

        has_base = bool(owned) and complete
        included: list[Adjustment] = []

        def value_of(adjustment: Adjustment, base: Decimal) -> Decimal | None:
            label = adjustment_label(adjustment)

            if adjustment.amount is not None:
                amount = self.money(adjustment.amount, label.lower())

                # Both stated ("GST 18%, 360"): the amount is what was
                # charged, but it must fit the percentage (bills round,
                # so within a rupee).
                if amount is not None and adjustment.percent is not None and has_base:
                    percent = self.percent(adjustment.percent, label.lower())
                    if percent is not None:
                        expected = (base * percent / 100).quantize(PAISA, ROUND_HALF_UP)
                        if abs(expected - amount) > 1:
                            self.problems.append(
                                f"{label} {percent}% of {base:,.2f} is {expected:,.2f}, "
                                f"but you said {amount:,.2f}."
                            )
                            return None

                return amount

            if adjustment.percent is not None:
                percent = self.percent(adjustment.percent, label.lower())
                if percent is None:
                    return None
                if not has_base:
                    # "Paid 1,180 including 18% GST": the total says it all.
                    if total_stated:
                        self.notes.append(f"Includes {label} ({percent}%).")
                    else:
                        self.problems.append(
                            f"{label} is {percent}%, but of what? Give the price before it."
                        )
                    return None
                return (base * percent / 100).quantize(PAISA, ROUND_HALF_UP)

            # Mentioned without an amount: with a final total stated ("1,850
            # including tax"), it's already inside that total.
            if total_stated:
                included.append(adjustment)
                self.notes.append(f"Includes {label.lower()}.")
            else:
                self.problems.append(f"How much was the {label.lower()}?")
            return None

        # The same words can't state something more times than they appear
        # in the text: an adjustment cited again beyond that is a repeat.
        cited: dict[tuple, int] = {}
        stated_once = []
        for adjustment in extraction.adjustments:
            evidence = (adjustment.amount or adjustment.percent)
            key = (
                adjustment.kind,
                adjustment.effect,
                (adjustment.label or "").casefold(),
                adjustment.amount.value if adjustment.amount else None,
                adjustment.percent.value if adjustment.percent else None,
            )
            cited[key] = cited.get(key, 0) + 1
            appears = _normalize(self.text).count(_normalize(evidence.evidence)) if evidence else 0
            # (Words not in the text at all are refused by the evidence check.)
            if appears and cited[key] > appears:
                self.notes.append(f"{adjustment_label(adjustment)} was listed twice; it's counted once.")
                continue
            stated_once.append(adjustment)

        # An adjustment whose kind contradicts what it does can't be
        # stored as either; it's asked about.
        adjustments = []
        for adjustment in stated_once:
            if fits_effect(adjustment):
                adjustments.append(adjustment)
            else:
                label = (adjustment.label or adjustment.kind).lower()
                self.problems.append(
                    f"Does the {label} add to the bill or take money off it?"
                )
                complete = False

        # Who or which items each adjustment was said to be for; None when
        # that couldn't be checked (a problem is recorded).
        scopes: dict[int, tuple[list[str], list[str]]] = {}
        for adjustment in adjustments:
            scope = self.scope_of(
                adjustment, f"the {adjustment_label(adjustment).lower()}", [item.name for item in items]
            )
            if scope is None:
                complete = False
            else:
                scopes[id(adjustment)] = scope

        def scoped_base(adjustment: Adjustment, whole: Decimal) -> Decimal:
            # A percentage of particular items is of those items' prices.
            names = scopes.get(id(adjustment), ([], []))[1]
            if not names:
                return whole
            return sum((item.amount for item in items if item.name in names), ZERO)

        lines: list[Line] = []

        def line_for(adjustment: Adjustment, value: Decimal, stage: int) -> Line:
            owners, names = scopes.get(id(adjustment), ([], []))
            return Line(
                label=adjustment_label(adjustment),
                amount=value,
                adds=adjustment.effect == "adds",
                stage=stage,
                taxable=adjustment.effect == "adds" and adjustment.kind not in ("tax", "tip"),
                owners=owners,
                items=names,
            )

        # Subtractions first: they apply to the items.
        deductions: list[ExpenseDeductionCreate] = []
        breakdown = [f"{'Items' if items else 'Price'} {subtotal:,.2f}"]

        for adjustment in adjustments:
            if adjustment.effect != "subtracts" or id(adjustment) not in scopes:
                continue
            value = value_of(adjustment, scoped_base(adjustment, subtotal))
            if value is None:
                complete = False
                continue
            deductions.append(as_deduction(adjustment, value))
            lines.append(line_for(adjustment, value, 1))
            breakdown.append(f"- {adjustment_label(adjustment)} {value:,.2f}")

        discount = sum((d.amount for d in deductions), ZERO)

        # Additions next, in the order a real bill applies them: charges
        # (service, delivery, packaging, fees, tips) on the items after
        # discounts; then taxes on that plus the charges, except tips,
        # which aren't taxed.
        charges: list[ExpenseChargeCreate] = []
        taxable = subtotal - discount

        def add(adjustment: Adjustment, base: Decimal, stage: int) -> Decimal | None:
            value = value_of(adjustment, scoped_base(adjustment, base))
            # A charge of nothing ("GST 0%") changes nothing and isn't kept.
            if value is not None and value > 0:
                charges.append(as_charge(adjustment, value))
                lines.append(line_for(adjustment, value, stage))
                breakdown.append(f"+ {adjustment_label(adjustment)} {value:,.2f}")
            return value

        additions = [a for a in adjustments if a.effect == "adds" and id(a) in scopes]
        charges_first = [a for a in additions if a.kind != "tax"]
        taxes = [a for a in additions if a.kind == "tax"]

        taxable_charges: list[Decimal] = []
        for adjustment in charges_first:
            value = add(adjustment, subtotal - discount, 2)
            if value is None:
                complete = False
            elif adjustment.kind != "tip":
                taxable += value
                taxable_charges.append(value)

        def fits(adjustment: Adjustment, base: Decimal) -> bool:
            # Whether a stated percentage and amount agree on this base.
            try:
                amount = Decimal(adjustment.amount.value.replace(",", ""))
                percent = Decimal(adjustment.percent.value.replace(",", "").rstrip("%"))
            except (AttributeError, InvalidOperation):
                return False
            return abs(scoped_base(adjustment, base) * percent / 100 - amount) <= 1

        goods = subtotal - discount
        # Every base a tax could have been worked out on: the items plus
        # any combination of the taxable charges.
        bases = sorted({
            goods + sum(combo, ZERO)
            for size in range(len(taxable_charges) + 1)
            for combo in combinations(taxable_charges, size)
        })
        for adjustment in taxes:
            # On the items and every taxable charge, unless the user's own
            # numbers fit only another base: then that one (on the items
            # alone, it's shared like the items are).
            base, stage = taxable, 3
            if not fits(adjustment, taxable):
                fitting = [b for b in bases if fits(adjustment, b)]
                if len(fitting) == 1:
                    base, stage = fitting[0], (2 if fitting[0] == goods else 3)
            if add(adjustment, base, stage) is None:
                complete = False

        added = sum((charge.amount for charge in charges), ZERO)
        # In the order the user gave them, for the questions about them.
        included.sort(key=lambda adjustment: extraction.adjustments.index(adjustment))

        # One item with no price, and a total stated: the item is what the
        # total leaves, as long as nothing else is unknown (no percentage
        # needs the missing price, no charge is left to the total too).
        # Otherwise each unpriced item is a question.
        missing: ExtractedItem | None = None
        if (
            total_stated
            and len(unpriced) == 1
            and not included
            and all(a.amount is not None for a in extraction.adjustments)
        ):
            missing = unpriced[0][0]
        else:
            for extracted, _ in unpriced:
                self.problems.append(f"What did the {extracted.name} cost?")

        # Only a full set of parts gives a final amount; otherwise the
        # stated total (or the payments) decides.
        final = subtotal - discount + added if has_base and complete else None

        # Show the working whenever something changed the items' sum.
        shown = None
        if final is not None and (charges or discount):
            shown = " ".join(breakdown) + f" = {final:,.2f}"

        return Bill(
            items=items,
            deductions=deductions,
            charges=charges,
            final=final,
            breakdown=shown,
            has_base=has_base,
            base=subtotal,
            included=included,
            owned=owned,
            part_lines=part_lines,
            part_items=part_items,
            lines=lines,
            missing=missing,
            missing_quantity=unpriced[0][1] if missing else Decimal("1"),
        )

    def price_from_total(self, extraction: ExpenseExtraction, total: Decimal) -> dict[int, Decimal] | None:
        """
        Explanation:
            The price of the one item with none stated, when the stated
            final total and the bill's percentages fix it ("1,180 including
            18% GST" -> 1,000). The bill is worked out exactly as saved for
            two trial prices; the price that gives the total is kept only
            if the bill then comes to the total to the paisa.

        Parameters:
            extraction: What the model extracted.
            total: The stated final total.

        Returns:
            {item index: price}, or None when it isn't fixed that way.
        """
        unpriced = [
            index for index, item in enumerate(extraction.items)
            if item.line_total is None and item.unit_price is None and not item.portions
        ]
        if len(unpriced) != 1 or not any(a.percent is not None for a in extraction.adjustments):
            return None
        index = unpriced[0]

        def final(price: Decimal) -> Decimal | None:
            # A trial: whatever it says or asks is thrown away.
            kept = (len(self.problems), len(self.notes), len(self.choices))
            bill = self.build_bill(extraction, total_stated=True, derived={index: price})
            del self.problems[kept[0]:], self.notes[kept[1]:], self.choices[kept[2]:]
            return bill.final

        low, high = Decimal(100), Decimal(1000)
        at_low, at_high = final(low), final(high)
        if at_low is None or at_high is None or at_low == at_high:
            return None
        price = (low + (total - at_low) * (high - low) / (at_high - at_low)).quantize(PAISA, ROUND_HALF_UP)
        if price <= 0 or final(price) != total:
            return None
        return {index: price}

    def complete_from_total(self, bill: Bill, total: Decimal, listed_only: bool) -> None:
        """
        Explanation:
            Use a stated total to finish a bill whose parts leave exactly
            one amount open. Both are the same rule as "I paid the rest":

            - one item with no price: it costs what the total leaves;
            - items listed, but only some of them ("650 in all, the nachos
              were 150"), with no taxes or discounts that could explain the
              difference: the rest is everything else that was bought,
              treated like any item that is nobody's own.

            Anything that can't be finished this way is left for the usual
            checks (the total must agree with the parts).

        Parameters:
            bill: The bill from build_bill; changed in place.
            total: The stated total.
            listed_only: True when the bill is only items (no adjustments
                and no subtotal), so a shortfall can only be more items.
        """
        priced = sum((item.amount for item in bill.items), ZERO)
        rest = total - bill.parts

        if bill.missing is not None:
            name = bill.missing.name
            if rest <= 0:
                self.problems.append(
                    f"What did the {name} cost? The rest of the bill already makes up the total."
                )
                return

            try:
                item = ExpenseItemCreate(
                    name=name, quantity=bill.missing_quantity, unit=bill.missing.unit, amount=rest
                )
            except ValidationError:
                self.problems.append(f"I couldn't read the item {name!r}.")
                return

            portioned = self.portions_of(bill.missing, rest, bill.missing_quantity)
            if portioned is None:
                return

            bill.items.append(item)
            bill.owned.extend(portioned[1])
            bill.part_lines.extend([name] * len(portioned[1]))
            bill.part_items.extend([len(bill.items) - 1] * len(portioned[1]))
            bill.base = priced + rest
            bill.has_base = True
            bill.final = total
            bill.missing = None
            self.notes.append(f"The {name} is what the total leaves: {rest:,.2f}.")
            return

        if listed_only and bill.items and bill.final is not None and 0 < rest:
            bill.items.append(ExpenseItemCreate(name="Everything else", amount=rest))
            bill.owned.append(("Everything else", rest, []))
            bill.part_lines.append("Everything else")
            bill.part_items.append(len(bill.items) - 1)
            bill.base = priced + rest
            bill.final = total
            self.notes.append(
                f"The items listed come to {priced:,.2f}; the other {rest:,.2f} is "
                "saved as “Everything else”."
            )

    def reconcile(self, bill: Bill, total: Decimal) -> None:
        """
        Explanation:
            Finish a bill whose parts aren't complete from the total, when
            that's plain arithmetic: exactly one adjustment said to be
            inside the total with no amount ("1,100 including tax") is
            what the total leaves.

            Nothing the user said is ever dropped to make the numbers fit;
            parts that still disagree with the total are a question (see
            settle_total).

        Parameters:
            bill: The bill from build_bill; changed in place.
            total: The expense's final amount.
        """
        if bill.final is not None or not bill.has_base or len(bill.included) != 1:
            return

        gap = total - bill.parts
        adjustment = bill.included[0]
        label = adjustment_label(adjustment)

        if adjustment.effect == "adds" and gap > 0:
            bill.charges.append(as_charge(adjustment, gap))
            bill.lines.append(Line(label=label, amount=gap, adds=True, stage=4))
            self.notes.append(f"{label} worked out from the total: {gap:,.2f}.")
        elif adjustment.effect == "subtracts" and gap < 0:
            bill.deductions.append(as_deduction(adjustment, -gap))
            bill.lines.append(Line(label=label, amount=-gap, adds=False, stage=4))
            self.notes.append(f"{label} worked out from the total: {-gap:,.2f}.")

    def settle_total(self, bill: Bill, total: Decimal) -> Decimal | None:
        """
        Explanation:
            Check the stated total against the bill's parts. When they
            disagree, nothing is guessed: it's a question, with the two
            answers that can be applied exactly offered as choices, and
            applied here once the user picks one (self.decisions):

                keep_total   the total is right: every part is kept, and
                             the difference is its own line, "Difference
                             from the total" (a charge if the total is more,
                             a deduction if it's less)
                keep_parts   the parts are right: the total is what they
                             come to (only when every part is known)

        Parameters:
            bill: The bill; changed in place for keep_total.
            total: The stated total.

        Returns:
            The final amount, or None while the question is open.
        """
        # Without a price before adjustments ("paid 900 after a 100
        # discount") the total is the only amount there is; the charges
        # must still leave something that was bought.
        if not bill.has_base:
            if bill.charges and bill.charged >= total + bill.deducted:
                self.problems.append(
                    f"The charges come to {bill.charged:,.2f}, which leaves nothing for what "
                    f"was bought in a total of {total:,.2f}. Which amount is wrong?"
                )
                return None
            return total

        parts = bill.final if bill.final is not None else bill.parts
        if parts == total:
            return total

        # Several adjustments said to be inside the total with no amounts:
        # together they're the difference, but each one's share of it isn't
        # known.
        if len(bill.included) > 1 and total > parts and "keep_total" not in self.decisions:
            names = [adjustment_label(a).lower() for a in bill.included]
            listed = ", ".join(names[:-1]) + f" and {names[-1]}"
            self.problems.append(
                f"The {listed} come to {total - parts:,.2f} together. How much was each?"
            )
            return None

        complete = bill.final is not None

        if "keep_parts" in self.decisions and complete and parts > 0:
            self.notes.append(
                f"You said the parts are right, so the total is {parts:,.2f}, not {total:,.2f}."
            )
            return parts

        if "keep_total" in self.decisions:
            gap = total - parts
            if gap > 0:
                bill.charges.append(ExpenseChargeCreate(kind="other", label=DIFFERENCE_LABEL, amount=gap))
                bill.lines.append(Line(label=DIFFERENCE_LABEL, amount=gap, adds=True, stage=4))
            elif gap < 0:
                bill.deductions.append(
                    ExpenseDeductionCreate(kind="other", label=DIFFERENCE_LABEL, amount=-gap)
                )
                bill.lines.append(Line(label=DIFFERENCE_LABEL, amount=-gap, adds=False, stage=4))
            self.notes.append(
                f"You said the total of {total:,.2f} is right; the parts come to "
                f"{parts:,.2f}, so the {abs(gap):,.2f} between them is kept as "
                f"“{DIFFERENCE_LABEL}”."
            )
            bill.final = total
            return total

        working = bill.breakdown if complete and bill.breakdown else None
        self.problems.append(
            f"The bill works out to {parts:,.2f}"
            + (f" ({working})" if working else "")
            + f", but the total you gave is {total:,.2f}."
        )
        self.choices.append(DraftChoice(decision="keep_total", label=f"The total {total:,.2f} is right"))
        if complete and parts > 0:
            self.choices.append(
                DraftChoice(decision="keep_parts", label=f"The parts are right ({parts:,.2f})")
            )
        return None

    # ---------- who shares the cost ----------

    @staticmethod
    def person_key(person: DraftPerson) -> tuple:
        """What makes two draft people the same person."""
        return (person.kind, person.contact_id, person.new_key)

    def effective_split(self, extraction: ExpenseExtraction, bill: Bill) -> ExtractedSplit | None:
        """
        Explanation:
            How the cost is shared, from what the user said and nothing
            else:

                a split is stated             -> that split
                items say whose they are      -> split by items
                the expense is for someone    -> their cost (evenly if several;
                                                 "mine" makes it the user's)
                none of these                 -> None (see build: the user's
                                                 only when nobody else is
                                                 involved, else asked)

            An item said to be someone's stays theirs whatever the split,
            so an even split with such items becomes a split by items, and
            the even split's people share what isn't anyone's own. Stated
            amounts or percentages are the whole allocation as given.

            Who shares what isn't anyone's own is never guessed from who
            paid or who was there, and never defaults to the user when
            anyone else is involved: it's the people the split names, else
            the people the expense is for, else asked (see split_shares).
            Like numbers, a split and whose cost it is must be backed by
            the user's words.

        Parameters:
            extraction: What the model extracted.
            bill: The bill, for the items' owners.

        Returns:
            The split to use, or None (then it's all the user's).
        """
        split = extraction.split
        if split is not None and not self.stated(split.evidence):
            self.problems.append("I couldn't find where you said how it's split.")
            self.allocation_refused = True
            return None

        # The same words can't state two things: a share quoting exactly the
        # money of a repayment in this message, or of a payment for this
        # bill ("my wife covered 2,000"), is that money, not a share.
        paid_words = {
            _normalize(payment.amount.evidence) for payment in extraction.payments if payment.amount is not None
        }
        taken = self.repaid_words | paid_words
        if split is not None and taken:
            kept = [
                share for share in split.shares
                if share.amount is None or _normalize(share.amount.evidence) not in taken
            ]
            if len(kept) != len(split.shares):
                # Split by stated amounts whose amounts were all the
                # repayment's: it says nothing of its own.
                says_nothing = split.method in ("amounts", "percent") and not any(
                    share.amount or share.percent for share in kept
                )
                split = None if not kept or says_nothing else split.model_copy(update={"shares": kept})

        for_refs = list(dict.fromkeys(extraction.for_refs))
        if for_refs and not self.stated(extraction.for_evidence):
            self.problems.append("I couldn't find where you said whose cost this is.")
            self.allocation_refused = True
            return None

        if split is not None and not self.only_people([share.ref for share in split.shares]):
            return None
        if not self.only_people(for_refs):
            return None

        someones = any(refs for _, _, refs in bill.owned)

        if split is not None:
            shares = split.shares
            # A split says the cost is shared. One naming nobody but the
            # user is shared by the people in this expense, when there are
            # others (said in a note); with nobody else in it, who with is
            # asked (split_shares).
            if split.method != "items" and {share.ref for share in shares} <= {SELF_REF}:
                people = self.people_in_expense()
                stated_any = any(share.amount or share.percent for share in shares)
                if len(people) > 1 and split.method == "equal":
                    # With one other person it can only be with them; with
                    # several, being mentioned isn't sharing it: asked.
                    with_whom = (people if len(people) == 2 or split.people_count is not None
                                 else self.ask_split_with(people))
                    if with_whom is None:
                        self.allocation_refused = True
                        return None
                    shares = [ExtractedShare(ref=ref) for ref in with_whom]
                    self.note_people(with_whom)
                elif len(people) > 1 and not stated_any:
                    self.problems.append("How is it split? You said it's shared, but not how.")
                    return None
                elif not stated_any or len(people) == 1:
                    shares = []
                # Otherwise the user's stated share stays, and the rest is
                # worked out in split_shares (with_the_rest).
            # A split by items with no group of its own: what isn't anyone's
            # own is for whoever the whole expense is for, if that's said.
            if split.method == "items" and not shares:
                shares = [{"ref": ref} for ref in for_refs]
            method = "items" if split.method == "equal" and someones else split.method
            return ExtractedSplit(method=method, shares=shares, evidence=split.evidence,
                                  people_count=split.people_count)

        if someones:
            self.note_even(for_refs, "what isn't anyone's own")
            return ExtractedSplit(
                method="items",
                shares=[{"ref": ref} for ref in for_refs],
                evidence=extraction.for_evidence or "",
            )

        if for_refs:
            self.note_even(for_refs, "this")
            return ExtractedSplit(
                method="equal",
                shares=[{"ref": ref} for ref in for_refs],
                evidence=extraction.for_evidence or "",
            )

        return None

    def ask_whose(self, what: str) -> list[str] | None:
        """
        Explanation:
            Who a cost nothing in the message allocates belongs to. Being
            in an expense ("with Aadhya") doesn't make someone an owner, so
            with anyone else in it, it's asked, with one-tap answers built
            from the people in it: all mine, split equally, all theirs.
            With nobody else in it, it's the user's. A cost of the user's
            own household is nobody's debt to anyone: it stays with
            whoever paid it, said in a note, and the same answers change it.

        Parameters:
            what: What it's about, for the question ("this", "the pizza").

        Returns:
            The refs it belongs to (shared equally), or None while asked.
        """
        people = self.people_in_expense()
        if len(people) == 1:
            return people

        others = [ref for ref in people if ref != SELF_REF and self.people.get(ref)]
        if len(others) < len(people) - 1:
            # Someone in it isn't identified yet (already asked): whose it
            # is can only be asked once they are.
            return None
        names = [self.called.get(ref, self.people[ref].name) for ref in others]
        everyone = ", ".join(["you", *names][:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]
        answers = [
            ("owner:me", "All mine", [SELF_REF]),
            ("owner:equal", f"Split equally with {names[0]}" if len(names) == 1
             else f"Split equally between {everyone}", people),
            *((f"owner:{_normalize(self.people[ref].name)}", f"All {name}'s", [ref])
              for ref, name in zip(others, names)),
        ]
        for decision, _, refs in answers:
            if decision in self.decisions:
                return refs

        payers = list(dict.fromkeys(self.payer_refs or [SELF_REF]))
        if self.household and len(payers) == 1 and payers[0] in people:
            if payers[0] == SELF_REF:
                whose = "yours, since you paid" if self.payer_refs else "yours"
            else:
                whose = f"{names[others.index(payers[0])]}'s, since they paid"
            self.notes.append(f"A household cost, so nobody owes anybody for it: it's counted as {whose}.")
            for decision, label, refs in answers:
                if refs != payers and all(choice.decision != decision for choice in self.choices):
                    self.choices.append(DraftChoice(decision=decision, label=label))
            return payers

        with_whom = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
        self.problems.append(f"Whose is {what}? Being with {with_whom} doesn't say whose it is.")
        for decision, label, _ in answers:
            if all(choice.decision != decision for choice in self.choices):
                self.choices.append(DraftChoice(decision=decision, label=label))
        return None

    def owed_or_treat(
        self,
        extracted: list[ExtractedPayment],
        payments: list[DraftPayment],
        participants: list[DraftShare],
    ) -> list[DraftShare]:
        """
        Explanation:
            When people other than the user paid all of a cost that's only
            the user's ("Dad paid for my ticket"), it's either owed back or
            their treat. A treat is the payers' own cost (each what they
            paid), so it's nobody's spending to repay and moves no balance.
            Owed back stays the user's share, paid by them. Read from the
            text ("I owe him", "his treat") or a payment repaid in this
            message; otherwise asked, with one-tap answers.

        Returns:
            The shares to use.
        """
        if not payments or any(p.person.kind == "me" for p in payments):
            return participants
        if len(participants) != 1 or participants[0].person.kind != "me":
            return participants

        names = joined([p.person.name for p in payments])
        # What the text says, only when its words are there.
        says = {p.owed_back for p in extracted if p.owed_back != "unsaid" and self.stated(p.owed_back_evidence)}
        owed = ("owe_payer" in self.decisions or "owed" in says
                or any(identity(p.person) in self.repaid_to for p in payments))
        treat = "treat" in self.decisions or ("treat" in says and not owed)

        if treat:
            self.notes.append(f"{names[0].upper()}{names[1:]} paid for it and nothing is owed, so it isn't your spending.")
            totals: dict[tuple, DraftShare] = {}
            for payment in payments:
                key = identity(payment.person)
                if key in totals:
                    totals[key].share_amount += payment.amount
                else:
                    totals[key] = DraftShare(person=payment.person, share_amount=payment.amount)
            return list(totals.values())
        if owed:
            return participants

        self.problems.append(f"{names[0].upper()}{names[1:]} paid for something that's yours. Do you owe it back?")
        for decision, label in (("owe_payer", f"Yes, I owe {names}"), ("treat", "No, nothing is owed")):
            if all(choice.decision != decision for choice in self.choices):
                self.choices.append(DraftChoice(decision=decision, label=label))
        return participants

    def unnamed_group(self, split: ExtractedSplit | None, shared: Decimal | None) -> tuple[int, Decimal | None] | None:
        """
        (how many share it, the user's even share or None) when the split
        says more people share it than it names; else None.
        """
        if split is None or split.people_count is None or shared is None:
            return None
        count = self.money(split.people_count, "number of people")
        if count is None or count != count.to_integral_value() or count <= len(split.shares):
            return None
        mine = allocate(shared, [Decimal(1)] * int(count))[0] if split.method == "equal" else None
        return int(count), mine

    def ask_split_with(self, people: list[str]) -> list[str] | None:
        """
        Who an even split that named nobody is with, when several people
        are in the expense: everyone, or the user and one of them, as the
        user picked; else asked, with one-tap answers.
        """
        others = [ref for ref in people if ref != SELF_REF and self.people.get(ref)]
        if len(others) < len(people) - 1:
            return None  # someone isn't identified yet (already asked)
        answers = [("split_with:everyone", "Everyone: " + self.who(people), people)]
        answers += [(f"split_with:{_normalize(self.people[ref].name)}", f"Just you and {self.people[ref].name}",
                     [SELF_REF, ref]) for ref in others]
        for decision, _, refs in answers:
            if decision in self.decisions:
                return refs
        self.problems.append(f"Who is it split equally with? You mentioned {self.who(others)}.")
        for decision, label, _ in answers:
            if all(choice.decision != decision for choice in self.choices):
                self.choices.append(DraftChoice(decision=decision, label=label))
        return None

    def note_people(self, refs: list[str]) -> None:
        """Say who a split nobody was named for is shared by, so it's never a silent choice."""
        names = ["you" if ref == SELF_REF else self.people[ref].name for ref in refs if self.people.get(ref)]
        if len(names) == len(refs):
            listed = ", ".join(names[:-1]) + f" and {names[-1]}"
            self.notes.append(f"Shared between {listed}: the people in this expense.")

    def with_the_rest(self, split: ExtractedSplit, stated: list[Decimal | None], total: Decimal) -> list[str]:
        """
        The split's people, completed when its stated shares leave part of
        the total to nobody: that part is the share of the one person in
        this expense the split doesn't list (derived, never asked). With
        several such people, whose it is stays unknown (asked by
        fill_the_rest).
        """
        refs = [share.ref for share in split.shares]
        known = sum((amount for amount in stated if amount is not None), ZERO)
        if None in stated or known >= total:
            return refs
        unlisted = [ref for ref in self.people_in_expense() if ref not in refs]
        if len(unlisted) == 1:
            return [*refs, unlisted[0]]
        if unlisted:
            names = [self.people[ref].name if ref != SELF_REF else "you" for ref in unlisted if self.people.get(ref)]
            self.problems.append(
                f"The shares you gave come to {known}; whose is the other {total - known}: "
                + ", ".join(names[:-1]) + f" or {names[-1]}?"
            )
        return refs

    def shares_from_settlement(
        self, extraction: ExpenseExtraction, stated: list[Decimal | None], total: Decimal, note: bool = True
    ) -> list[DraftShare] | None:
        """
        Explanation:
            The shares, when no split was given but the same message has a
            repayment that settles what its payer owed for this expense:
            money only ever goes from who owed to who was owed, so the
            payer's share is what they paid for the expense plus what they
            paid back ("I paid 900, Aadhya 300; I paid her the 100 that was
            my share" -> you 1,000). The rest is the other person's, when
            there's one other person in the expense; with several, whose it
            is stays unknown (None: asked as usual).

        Parameters:
            extraction: The expense, for who paid what.
            stated: Each payment's amount as worked out (None: not stated).
            total: What the shares add up to.

        Returns:
            The shares, or None when this doesn't settle them.
        """
        # An organization can settle its part too ("the office reimbursed
        # me"), though being mentioned doesn't make it one of the people.
        candidates = [*self.people_in_expense(), *(ref for ref in self.people if ref in self.organizations)]
        refs = {identity(p): ref for ref in candidates if (p := self.people.get(ref))}
        found = [
            (refs[payer], refs[receiver], money)
            for (payer, receiver), money in self.settled.items()
            if payer in refs and receiver in refs
        ]
        if len(found) != 1:
            return None
        debtor, creditor, money = found[0]
        people = list(dict.fromkeys(
            [*self.people_in_expense(), *(ref for ref in (debtor, creditor) if ref in self.organizations)]
        ))
        if len(people) < 2:
            return None

        paid_back = self.money(money, "amount paid back")
        if paid_back is None:
            return None
        payments = [amount for payment, amount in zip(extraction.payments, stated) if payment.payer_ref == debtor]
        if None in payments:
            return None
        paid = sum(payments, ZERO)
        share = paid + paid_back
        if share > total:
            self.problems.append(
                f"What was paid and paid back comes to {share:,.2f}, more than the whole {total:,.2f}."
            )
            return []

        who = self.whose([debtor])
        who = who[:1].upper() + who[1:]
        if note:
            self.notes.append(
            f"{who} share is what was paid for it ({paid:,.2f}) plus what was paid back ({paid_back:,.2f}): "
            f"{share:,.2f}."
        )
        # The rest is the other person's; with several others, whose it
        # is (or how they share it) is asked, never assumed.
        others = [ref for ref in people if ref != debtor]
        rest = total - share
        if len(others) == 1:
            owners = others
        else:
            owners = self.ask_rest(others, rest, f"{who} share is {share:,.2f}.")
            if owners is None:
                return []
        shares = [(debtor, share), *zip(owners, allocate(rest, [Decimal(1)] * len(owners)))]
        return [DraftShare(person=self.people[ref], share_amount=amount) for ref, amount in shares if amount > 0]

    def ask_rest(self, others: list[str], rest: Decimal, known: str) -> list[str] | None:
        """Whose the rest of a cost is when several others could own it: one-tap answers."""
        names = {ref: self.people[ref].name for ref in others if self.people.get(ref)}
        answers = [
            ("rest:equal", "Split equally between " + ", ".join(list(names.values())[:-1])
             + f" and {list(names.values())[-1]}", others),
            *((f"rest:{_normalize(name)}", f"All {name}'s", [ref]) for ref, name in names.items()),
        ]
        for decision, _, refs in answers:
            if decision in self.decisions:
                return refs
        self.problems.append(f"{known} Whose is the other {rest:,.2f}?")
        for decision, label, _ in answers:
            self.choices.append(DraftChoice(decision=decision, label=label))
        return None

    def agree_with_settlement(
        self,
        extraction: ExpenseExtraction,
        stated: list[Decimal | None],
        total: Decimal,
        participants: list[DraftShare],
        payments: list[DraftPayment],
    ) -> list[DraftShare]:
        """
        Explanation:
            Check the shares against a repayment in the same message that
            settles what its payer owed for this expense: after the shares,
            the payer must owe exactly what they paid back. When they don't,
            the shares that fit the repayment are offered next to the ones
            stated, as choices; the one picked is used.

        Returns:
            The shares to use ([] while the question is open).
        """
        by_key = {self.person_key(s.person): s.share_amount for s in participants}
        paid: dict[tuple, Decimal] = {}
        for payment in payments:
            paid[self.person_key(payment.person)] = paid.get(self.person_key(payment.person), ZERO) + payment.amount

        refs = {identity(p): ref for ref in self.people_in_expense() if (p := self.people.get(ref))}
        for (payer, receiver), money in self.settled.items():
            if payer not in refs or receiver not in refs:
                continue
            debtor = self.people[refs[payer]]
            amount = self.money(money, "amount paid back")
            key = self.person_key(debtor)
            owed = by_key.get(key, ZERO) - paid.get(key, ZERO)
            # Paying back what's owed, or part of it, fits the shares.
            if amount is None or 0 < amount <= owed:
                continue

            fitting = self.shares_from_settlement(extraction, stated, total, note=False)

            def listed(shares: list[DraftShare]) -> str:
                return ", ".join(f"{s.person.name} {s.share_amount:,.2f}" for s in shares)

            if fitting and owed <= 0:
                # By the shares as read, the payer owed nothing, so paying
                # back couldn't happen: the only reading that fits every
                # fact is the one where it settles what they owed.
                self.notes.append(
                    f"Read as {listed(fitting)}: with {listed(participants)}, "
                    f"{debtor.name if debtor.kind != 'me' else 'you'} would have owed nothing, "
                    f"so the {amount:,.2f} paid back couldn't be for it."
                )
                return fitting
            if not fitting:
                self.problems.append(
                    f"The shares don't fit the {amount:,.2f} paid back. Please say how it's split."
                )
                return []
            if "shares_from_repayment" in self.decisions:
                return fitting
            if "shares_as_stated" in self.decisions:
                return participants

            # More paid back than was owed: two readings, both offered.
            self.problems.append(
                f"The shares ({listed(participants)}) don't fit the {amount:,.2f} paid back, "
                f"which makes them {listed(fitting)}. Which is right?"
            )
            self.choices.append(DraftChoice(decision="shares_from_repayment", label=listed(fitting)))
            self.choices.append(DraftChoice(decision="shares_as_stated", label=listed(participants)))
            return []
        return participants

    def split_shares(self, split: ExtractedSplit, total: Decimal, bill: Bill) -> list[DraftShare]:
        """
        Explanation:
            Each person's share of the final amount, by the split's method.
            Whatever the method, the shares add up exactly to the total.

                equal    evenly, to the paisa
                amounts  as stated; at most one left out gets "the rest"
                percent  as stated; at most one left out gets the rest of 100%
                items    each person's own items (shared evenly when an item
                         is for several people); what isn't anyone's own is
                         shared evenly by the split's people; then every
                         discount, charge and tax line by line (see
                         share_by_lines)

            When a split by items names nobody to share what isn't anyone's
            own, that part is the user's only if nobody else is involved at
            all; otherwise who it was for is asked, never assumed.

        Parameters:
            split: The extracted split.
            total: The amount the shares add up to (the bill, before refunds).
            bill: The bill, for splitting by items.

        Returns:
            The shares, or [] with a problem recorded.
        """
        refs = [share.ref for share in split.shares]

        if len(set(refs)) != len(refs):
            self.problems.append("Someone is listed twice in the split. Please rephrase.")
            return []

        # A split that names nobody to share with is asked about, never
        # taken as "all yours".
        if not refs and split.method != "items":
            self.problems.append("Is this shared with anyone? If so, who with?")
            return []

        amounts: list[Decimal] | None
        # Who shares what isn't anyone's own (for refunds of such items).
        self.sharers = refs

        if split.method == "equal":
            # Everyone shares everything alike, so each item too.
            self.items_follow_split = True
            amounts = allocate(total, [Decimal(1)] * len(refs))

        elif split.method == "amounts":
            stated = [self.money(share.amount, "share") for share in split.shares]
            # Same rule as payments: a failed share isn't "the rest".
            unreadable = any(
                share.amount is not None and amount is None
                for share, amount in zip(split.shares, stated)
            )
            if not unreadable:
                refs = self.with_the_rest(split, stated, total)
                stated += [None] * (len(refs) - len(stated))
                self.sharers = refs
            amounts = None if unreadable else self.fill_the_rest(stated, total, "shares")

        elif split.method == "percent":
            percents = [
                self.percent(share.percent, "share") if share.percent else None
                for share in split.shares
            ]
            unreadable = any(
                share.percent is not None and percent is None
                for share, percent in zip(split.shares, percents)
            )
            if not unreadable:
                refs = self.with_the_rest(split, percents, Decimal(100))
                percents += [None] * (len(refs) - len(percents))
                self.sharers = refs
            filled = None if unreadable else self.fill_the_rest(percents, Decimal(100), "percentages")
            amounts = allocate(total, filled) if filled else None

        else:  # items
            if not bill.owned:
                self.problems.append("It's split by items, but I couldn't find the items.")
                return []

            if not refs and not any(item_refs for _, _, item_refs in bill.owned):
                self.problems.append("It's split by items, but I couldn't tell whose items were whose.")
                return []

            # What isn't anyone's own goes to the split's people. With nobody
            # named, it can only be the user's when nobody else is involved;
            # otherwise it's asked.
            sharers = refs
            unclaimed = [name for name, _, item_refs in bill.owned if not item_refs]
            if unclaimed and not sharers:
                names = " and ".join(f"the {name}" for name in dict.fromkeys(unclaimed))
                asked = self.ask_whose(names)
                if asked is None:
                    return []
                sharers = asked

            # Everyone with a part joins the split, in order of appearance,
            # and so does anyone an adjustment is said to be for.
            owners_named = [ref for _, _, item_refs in bill.owned for ref in item_refs]
            line_owners = [ref for line in bill.lines for ref in line.owners]
            refs = list(dict.fromkeys([*refs, *owners_named, *sharers, *line_owners]))

            self.sharers = sharers
            self.items_follow_split = True
            amounts = self.share_by_lines(refs, sharers, total, bill)

        if amounts is None:
            return []

        people = [self.person(ref) for ref in refs]

        return [
            DraftShare(person=person, share_amount=amount)
            for person, amount in zip(people, amounts)
            if person is not None and amount > 0
        ]

    def share_by_lines(
        self,
        refs: list[str],
        sharers: list[str],
        total: Decimal,
        bill: Bill,
    ) -> list[Decimal] | None:
        """
        Explanation:
            Each person's share when the bill is split by items, built the
            way the bill itself was: items first, then every adjustment
            line in the order it applies, each shared by one rule:

                said to be someone's     theirs (evenly if several)
                said to be for items     in proportion to each person's
                                         part of those items
                otherwise                in proportion to each person's
                                         part of what it was worked out on:
                                           deductions  their items
                                           charges     their items less
                                                       their deductions
                                           taxes       that plus their
                                                       taxable charges
                                           from the total  all of it so far

            Every line is split to the paisa, so the shares add up exactly
            to the total, and a note shows each person's working. (Refunds
            come off afterwards, only from the shares they belong to; see
            apply_refunds.)

        Parameters:
            refs: Everyone in the split, in order.
            sharers: Who shares the parts that are nobody's own.
            total: What the shares must add up to (the bill).
            bill: The bill, with its parts and lines.

        Returns:
            One amount per ref, or None with a problem recorded.
        """
        running = {ref: ZERO for ref in refs}
        items_of = {ref: ZERO for ref in refs}
        by_line: dict[str, dict[str, Decimal]] = {}
        working: dict[str, list[str]] = {ref: [] for ref in refs}

        for (_, price, item_refs), line_name in zip(bill.owned, bill.part_lines):
            owners = item_refs or sharers
            for ref, part in zip(owners, allocate(price, [Decimal(1)] * len(owners))):
                items_of[ref] += part
                running[ref] += part
                on_line = by_line.setdefault(line_name, {})
                on_line[ref] = on_line.get(ref, ZERO) + part

        for ref in refs:
            working[ref].append(f"items {items_of[ref]:,.2f}")

        taxable = dict(running)

        for stage in (1, 2, 3, 4):
            if stage == 2:
                taxable = dict(running)
            for line in (line for line in bill.lines if line.stage == stage):
                if line.owners:
                    weights = {ref: Decimal(1) for ref in line.owners}
                elif line.items:
                    weights = {
                        ref: sum((by_line.get(name, {}).get(ref, ZERO) for name in line.items), ZERO)
                        for ref in refs
                    }
                else:
                    weights = dict(taxable if stage == 3 else running)

                weights = {ref: weight for ref, weight in weights.items() if weight > 0}
                if not weights:
                    self.problems.append(f"I couldn't tell whose share the {line.label} is part of.")
                    return None

                sign = 1 if line.adds else -1
                for ref, part in zip(weights, allocate(line.amount, list(weights.values()))):
                    running[ref] += sign * part
                    if stage == 2 and line.taxable:
                        taxable[ref] += part
                    if part:
                        working[ref].append(f"{'+' if line.adds else '−'} {line.label} {part:,.2f}")

        if any(amount < 0 for amount in running.values()):
            self.problems.append("Someone's discounts come to more than their items. Please check them.")
            return None

        amounts = [running[ref] for ref in refs]

        # Every line was split exactly, so this holds whenever the parts
        # make up the total; if they don't, nothing is forced to fit.
        if sum(amounts, ZERO) != total:
            self.problems.append(
                f"The shares come to {sum(amounts, ZERO):,.2f}, but the total is {total:,.2f}."
            )
            return None

        if len(refs) > 1 and bill.lines:
            for ref, amount in zip(refs, amounts):
                name = self.who([ref])
                self.notes.append(f"{name.capitalize()}: {' '.join(working[ref])} = {amount:,.2f}")

        return amounts

    # ---------- repayments ----------

    def build_repayment(self, repayment: ExtractedRepayment, index: int = 0) -> RepaymentDraft:
        """
        Explanation:
            Money paid back between you and one person. Exactly one side
            must be you: a repayment between two other people doesn't
            change your balances, so it's a problem, not a record.

        Parameters:
            repayment: What the model extracted.

        Returns:
            The repayment draft, with any problems listed.
        """
        self.resolve_entities(repayment.entities)

        unknown = DraftPerson(kind="new", name="Someone")
        settled_currency: str | None = None
        from_person = self.person(repayment.from_ref) or unknown
        to_person = self.person(repayment.to_ref) or unknown

        amount = self.money(repayment.amount, "amount")
        other = to_person if from_person.kind == "me" else from_person

        if repayment.kind == "balance":
            # A debt that already existed is what the text says it was:
            # never read from the balance it's about to change.
            if repayment.amount is None:
                self.problems.append("How much was owed?")

        elif repayment.amount is None and repayment.amount_source == "their_share":
            # "She paid me her share": what this message's expenses leave
            # her owing (her share, less what she paid towards it).
            sign = 1 if from_person is other else -1
            owed = {c: a * sign for c, a in self.message_balances.get(identity(other), {}).items() if a * sign > 0}
            stated_currency = currency_of(repayment.currency, "") if repayment.currency else None
            if stated_currency in owed:
                settled_currency = stated_currency
            elif len(owed) == 1:
                settled_currency = next(iter(owed))
            if settled_currency is not None:
                amount = owed[settled_currency]
            elif not owed:
                self.problems.append(f"I couldn't find anything {other.name} owed for it to pay back.")
            else:
                self.problems.append("It's owed in several currencies. Which was paid back?")

        elif repayment.amount is None and repayment.amount_source == "everything_owed":
            # "Parth settled up": what the balance says, in whichever
            # currency is owed that way (asked when there are several).
            owed = self.owed_by(other, payer_is_other=from_person is other)
            if not owed:
                self.problems.append(f"There's nothing for {other.name} to settle.")
            else:
                picked = self.pick_currency(owed, index, "settle")
                if picked is not None:
                    amount = owed[picked]
                    settled_currency = picked
                    self.notes.append(f"Settles the full balance of {picked} {amount:,.2f}.")

        elif repayment.amount is None:
            self.problems.append("How much was paid back?")

        me_count = (from_person.kind == "me") + (to_person.kind == "me")
        if me_count == 2:
            self.problems.append("A repayment needs someone other than you.")
        elif me_count == 0 and "Someone" not in (from_person.name, to_person.name):
            self.problems.append(
                f"That's between {from_person.name} and {to_person.name}, not you, "
                "so it doesn't change your balances."
            )

        currency = settled_currency or currency_of(repayment.currency, self.user.default_currency)
        kind = self.money_kind(repayment, index, from_person, to_person, other, amount, currency)

        # A debt the records may already hold ("I still have to pay Riya
        # 300", after the dinner she paid for was saved): recording it again
        # would double it, so it's asked whenever one is already owed that way.
        if kind == "balance" and amount is not None and other.contact_id and "extra_debt" not in self.decisions:
            already = self.owed_by(other, payer_is_other=from_person is other).get(currency)
            if already:
                owing = f"{other.name} owes you" if from_person is other else f"you owe {other.name}"
                self.problems.append(
                    f"Your records already show {owing} {currency} {already:,.2f}. If that includes "
                    "this, there's nothing to save. Is it a separate debt?"
                )
                self.choices.append(DraftChoice(decision="extra_debt", label="Yes, it's a separate debt"))

        # Paying back in a currency nothing is owed in, while another
        # currency is owed that way: which debt it settles is asked.
        if (
            kind == "repayment" and amount is not None and not settled_currency and not repayment.for_share
            and other.contact_id
        ):
            owed = self.owed_by(other, payer_is_other=from_person is other)
            if owed and currency not in owed:
                picked = self.pick_currency({**owed, currency: amount}, index, "keep", paid=(currency, amount))
                if picked is not None and picked != currency:
                    self.notes.append(f"Paid as {currency} {amount:,.2f}, settling the {picked} "
                                      f"{owed[picked]:,.2f} owed.")
                    currency, amount = picked, owed[picked]

        # Paying back someone new, with no share of anything in this
        # message: nothing recorded was owed, so this turns the balance
        # around. Said, so it's never silent (an old debt is fine).
        if (
            kind == "repayment" and me_count == 1 and amount is not None and other.kind == "new"
            and identity(other) not in self.shares_in_message
        ):
            if from_person is other:
                self.notes.append(
                    f"Nothing recorded says {other.name} owed you anything, so this leaves you "
                    f"owing {other.name} {currency} {amount:,.2f}."
                )
            else:
                self.notes.append(
                    f"Nothing recorded says you owed {other.name} anything, so this leaves "
                    f"{other.name} owing you {currency} {amount:,.2f}."
                )

        used = {p.new_key for p in (from_person, to_person) if p.kind == "new" and p.new_key}
        self.confirm_new_people(used)

        return RepaymentDraft(
            excerpt=repayment.excerpt,
            date=self.date_of(repayment.date),
            amount=amount,
            currency=currency,
            method=repayment.method,
            kind=kind,
            from_person=from_person,
            to_person=to_person,
            new_contacts=[c for c in self.new_contacts if c.key in used],
            problems=list(dict.fromkeys(self.problems)),
            notes=list(dict.fromkeys(self.notes)),
            choices=self.choices,
        )

    def build_expected(self, repayment: ExtractedRepayment) -> ExpectedDraft | None:
        """
        Explanation:
            Money between the user and one person that's expected, not
            moved ("he'll return the 500 next week"). It changes nothing;
            the draft only lets the user remember it. None when it isn't
            between the user and someone else.

        Parameters:
            repayment: What the model extracted (status 'expected').

        Returns:
            The draft, or None.
        """
        self.resolve_entities(repayment.entities)
        from_person = self.person(repayment.from_ref)
        to_person = self.person(repayment.to_ref)
        if from_person is None or to_person is None or (from_person.kind == "me") == (to_person.kind == "me"):
            return None

        amount = self.money(repayment.amount, "amount")
        used = {p.new_key for p in (from_person, to_person) if p.kind == "new" and p.new_key}
        self.confirm_new_people(used)
        due = None
        if repayment.date:
            try:
                due = dt.date.fromisoformat(repayment.date)
            except ValueError:
                due = None

        return ExpectedDraft(
            excerpt=repayment.excerpt,
            from_person=from_person,
            to_person=to_person,
            amount=amount,
            currency=currency_of(repayment.currency, self.user.default_currency),
            kind=repayment.kind if repayment.kind in ("repayment", "loan", "reimbursement", "gift") else "repayment",
            due_date=due,
            new_contacts=[c for c in self.new_contacts if c.key in used],
            problems=list(dict.fromkeys(self.problems)),
            choices=self.choices,
        )

    def owed_by(self, other: DraftPerson, payer_is_other: bool) -> dict[str, Decimal]:
        """
        What's owed that the payer would be paying back, per currency:
        what's saved, and what this message's expenses add.
        """
        saved = self.balances.get(other.contact_id, {}) if other.contact_id else {}
        here = self.message_balances.get(identity(other), {})
        balances = {c: saved.get(c, ZERO) + here.get(c, ZERO) for c in dict.fromkeys([*saved, *here])}
        return {
            currency: (amount if payer_is_other else -amount)
            for currency, amount in balances.items()
            if (amount if payer_is_other else -amount) > 0
        }

    def pick_currency(self, choices: dict[str, Decimal], index: int, what: str,
                      paid: tuple[str, Decimal] | None = None) -> str | None:
        """
        Which currency's debt money between people is about: the only one,
        or the one the user picked; else asked, with one-tap answers.
        """
        picked = [c for c in choices if f"settle_currency:{index}:{c}" in self.decisions]
        if picked:
            return picked[0]
        if len(choices) == 1 and paid is None:
            return next(iter(choices))
        if paid is not None:
            paid_in, paid_amount = paid
            self.problems.append(
                f"Nothing is owed in {paid_in}. Does the {paid_in} {paid_amount:,.2f} settle another debt?"
            )
            labels = {c: (f"Keep it as {c} {a:,.2f}" if c == paid_in else f"It settles the {c} {a:,.2f} owed")
                      for c, a in choices.items()}
        else:
            self.problems.append("It's owed in several currencies. Which was settled?")
            labels = {c: f"The {c} {a:,.2f}" for c, a in choices.items()}
        for c, label in labels.items():
            self.choices.append(DraftChoice(decision=f"settle_currency:{index}:{c}", label=label))
        return None

    def money_kind(self, repayment: ExtractedRepayment, index: int, from_person: DraftPerson,
                   to_person: DraftPerson, other: DraftPerson, amount: Decimal | None,
                   currency: str) -> str | None:
        """
        What money between the user and someone was, as the text says, or
        as the user picked. When the text doesn't say, it's asked, with
        one-tap answers: never assumed to be paying back.
        """
        picked = [kind for kind in MONEY_KINDS if f"money_kind:{index}:{kind}" in self.decisions]
        if picked:
            return picked[0]
        if repayment.kind != "unclear":
            return repayment.kind

        they_paid = from_person is other
        how_much = f"{currency} {amount:,.2f}" if amount is not None else "this money"
        self.problems.append(
            f"What was the {how_much} {'from' if they_paid else 'to'} {other.name} for? You didn't say."
        )
        answers = {
            "repayment": f"{other.name} paid me back" if they_paid else f"I paid {other.name} back",
            "loan": f"{other.name} lent it to me" if they_paid else f"I lent it to {other.name}",
            "gift": "A gift, nothing owed",
        }
        for kind, label in answers.items():
            self.choices.append(DraftChoice(decision=f"money_kind:{index}:{kind}", label=label))
        return None

    def date_of(self, raw: str | None) -> dt.date:
        """A stated YYYY-MM-DD date, else today (also for nonsense)."""
        try:
            return dt.date.fromisoformat(raw) if raw else self.today
        except ValueError:
            return self.today

    # amounts with "the rest"
    def net_payments(
        self,
        extracted: list[ExtractedPayment],
        currency: str,
    ) -> tuple[list[Decimal | None], bool]:
        """
        Explanation:
            What each payer actually paid: the amount they handed over,
            less any change they got back ("paid 1,100, got 50 back" is
            1,050). Every number is evidence-checked; a payment whose
            numbers fail, or that makes no sense, is "unreadable" so it can
            never quietly become "the rest".

        Parameters:
            extracted: The extraction's payments (may be empty).
            currency: The expense's currency, for the notes.

        Returns:
            (one amount per payment, None where not stated; whether any
            payment was unreadable). With no payments: ([None], False),
            meaning you paid whatever the total is.
        """
        if not extracted:
            return [None], False

        amounts: list[Decimal | None] = []
        unreadable = False

        for payment in extracted:
            handed = self.money(payment.amount, "payment")
            change = self.money(payment.change, "change")

            # A number was given but failed its evidence check.
            if (payment.amount is not None and handed is None) or (
                payment.change is not None and change is None
            ):
                unreadable = True

            if change is not None:
                if handed is None:
                    self.problems.append(
                        f"You got {currency} {change:,.2f} back as change, "
                        "but how much did you hand over?"
                    )
                    unreadable = True
                elif change >= handed:
                    self.problems.append(
                        f"The change ({currency} {change:,.2f}) is more than what was "
                        f"handed over ({currency} {handed:,.2f})."
                    )
                    unreadable = True
                else:
                    self.notes.append(
                        f"Handed over {currency} {handed:,.2f}, "
                        f"{currency} {change:,.2f} back as change."
                    )
                    handed -= change

            amounts.append(handed)

        return amounts, unreadable

    def refund_amounts(self, extraction: ExpenseExtraction) -> list[tuple[ExtractedRefund, Decimal]]:
        """
        Explanation:
            Each refund's amount, evidence-checked like every number. A
            refund with no amount is asked about, never guessed.

        Parameters:
            extraction: What the model extracted.

        Returns:
            (refund, amount) for every refund whose amount is known.
        """
        known = []

        for refund in extraction.refunds:
            what = f"refund for {refund.label.lower()}" if refund.label else "refund"
            amount = self.money(refund.amount, what)
            if refund.amount is None:
                self.problems.append(f"How much was the {what}?")
            if amount is not None:
                known.append((refund, amount))

        return known

    def refund_recipients(
        self,
        refunds: list[tuple[ExtractedRefund, Decimal]],
        paid: list,
        date: dt.date,
        currency: str,
    ) -> list[DraftRefund | None]:
        """
        Explanation:
            Who got each refund back. Money comes back to someone who paid:
            the person the text names, if they paid; else, when one person
            paid, them (derived, and said in a note); with several payers
            and nobody named, it's asked.

        Parameters:
            refunds: Each refund and its amount.
            paid: The draft's payments, or the payers when their amounts
                aren't known yet.
            date: The expense's date, for refunds that don't give one.
            currency: For the notes.

        Returns:
            One per refund: it with its recipient, or None when that
            couldn't be told (a problem is recorded).
        """
        people = [item.person if isinstance(item, DraftPayment) else item for item in paid]
        payers = {self.person_key(person): person for person in people if person is not None}
        drafts = []

        for refund, amount in refunds:
            if refund.to_ref:
                person = self.person(refund.to_ref)
                if person is None:
                    drafts.append(None)
                    continue
                if self.person_key(person) not in payers:
                    self.problems.append(
                        f"The {currency} {amount:,.2f} refund went to {person.name}, who didn't "
                        "pay for this. A refund goes back to someone who paid."
                    )
                    drafts.append(None)
                    continue
            elif len(payers) == 1:
                [person] = payers.values()
                who = "you" if person.kind == "me" else person.name
                self.notes.append(f"The {currency} {amount:,.2f} refund went back to {who}, who paid.")
            else:
                self.problems.append(
                    f"Who got the {currency} {amount:,.2f} refund back? More than one person paid."
                )
                drafts.append(None)
                continue

            label = " ".join((refund.label or "").split())[:100] or None
            drafts.append(
                DraftRefund(
                    person=person,
                    amount=amount,
                    label=label,
                    date=self.date_of(refund.date) if refund.date else date,
                )
            )

        return drafts

    def apply_refunds(
        self,
        participants: list[DraftShare],
        refunds: list[tuple[ExtractedRefund, Decimal]],
        recipients: list[DraftRefund | None],
        bill: Bill,
        currency: str,
    ) -> list[DraftShare]:
        """
        Explanation:
            Take each refund off the shares it belongs to. Who got the money
            back is a separate fact (it's in the refund); whose share it
            lowers is never assumed to be everyone's:

                said whose share            theirs (evenly if several)
                said which item it was for  that item's owners, in
                                            proportion to their part of it
                only one person shares      theirs
                otherwise                   asked, with two exact answers:
                                            only the recipient's share, or
                                            everyone's in proportion

        Parameters:
            participants: The shares of the whole bill.
            refunds: Each refund and its amount.
            recipients: Who got each back (None where not known).
            bill: The bill, for which items' owners.
            currency: For messages.

        Returns:
            The shares after the refunds, or [] while a question is open.
        """
        if not participants or not refunds:
            return participants

        shares = {self.person_key(share.person): [share.person, share.share_amount] for share in participants}
        line_names = [item.name for item in bill.items]
        open_question = False

        for index, ((refund, amount), recipient) in enumerate(zip(refunds, recipients)):
            what = f"the {currency} {amount:,.2f} refund"
            scope = self.scope_of(refund, what, line_names)
            if scope is None:
                open_question = True
                continue
            owners, names = scope

            weights: dict[tuple, Decimal] = {}
            if owners:
                for ref in owners:
                    person = self.person(ref)
                    if person is not None:
                        weights[self.person_key(person)] = Decimal(1)
            elif names:
                for (_, price, item_refs), line in zip(bill.owned, bill.part_lines):
                    if line not in names:
                        continue
                    part_owners = item_refs or self.sharers
                    for ref, part in zip(part_owners, allocate(price, [Decimal(1)] * len(part_owners))):
                        person = self.person(ref)
                        if person is not None:
                            key = self.person_key(person)
                            weights[key] = weights.get(key, ZERO) + part
            elif len(shares) == 1:
                weights = {next(iter(shares)): Decimal(1)}
            elif recipient is not None and f"refund_owner:{index}" in self.decisions:
                weights = {self.person_key(recipient.person): Decimal(1)}
            elif f"refund_shared:{index}" in self.decisions:
                weights = {key: amount_now for key, (_, amount_now) in shares.items()}
            else:
                self.problems.append(f"Whose share does {what} come off? You didn't say.")
                if recipient is not None:
                    who = "your" if recipient.person.kind == "me" else f"{recipient.person.name}'s"
                    self.choices.append(
                        DraftChoice(decision=f"refund_owner:{index}", label=f"Only {who} share")
                    )
                self.choices.append(
                    DraftChoice(decision=f"refund_shared:{index}", label="Everyone's, in proportion")
                )
                open_question = True
                continue

            outside = [key for key in weights if key not in shares]
            if outside:
                self.problems.append(f"{what.capitalize()} comes off a share of someone who isn't sharing this cost.")
                open_question = True
                continue

            keys = [key for key, weight in weights.items() if weight > 0]
            for key, part in zip(keys, allocate(amount, [weights[key] for key in keys])):
                shares[key][1] -= part
            owners_of = ["your" if p.kind == "me" else f"{p.name}'s" for p in (shares[key][0] for key in keys)]
            whose = owners_of[0] if len(owners_of) == 1 else ", ".join(owners_of[:-1]) + f" and {owners_of[-1]}"
            self.notes.append(
                f"The {currency} {amount:,.2f} refund comes off {whose} share{'s' if len(owners_of) > 1 else ''}."
            )

        if open_question:
            return []

        if any(amount < 0 for _, amount in shares.values()):
            self.problems.append("A refund comes to more than that person's share. Please check it.")
            return []

        return [DraftShare(person=person, share_amount=amount) for person, amount in shares.values() if amount > 0]

    def item_owners(self, bill: Bill) -> list[list[DraftShare]]:
        """
        Explanation:
            Whose each item is, to save with it: the people it was said to
            be for, or, for a part that's nobody's own, the people the split
            says share such parts. An item any part of which isn't settled
            that way (e.g. a split by stated amounts) gets no owners: never
            guessed.

        Parameters:
            bill: The bill, with its parts.

        Returns:
            One list per item of bill.items: its owners and their parts
            (adding up to its price), or [] when not known.
        """
        per_item: list[dict[tuple, list] | None] = [{} for _ in bill.items]

        for (_, price, refs), index in zip(bill.owned, bill.part_items):
            if index is None or per_item[index] is None:
                continue
            owners = refs or (self.sharers if self.items_follow_split else [])
            people = [self.person(ref) for ref in owners]
            if not people or any(person is None for person in people):
                per_item[index] = None
                continue
            for person, part in zip(people, allocate(price, [Decimal(1)] * len(people))):
                key = self.person_key(person)
                entry = per_item[index].setdefault(key, [person, ZERO])
                entry[1] += part

        return [
            [DraftShare(person=p, share_amount=a) for p, a in owners.values() if a > 0] if owners else []
            for owners in per_item
        ]

    def infer_cash_change(
        self,
        amounts: list[Decimal | None],
        extracted: list[ExtractedPayment],
        total: Decimal,
        currency: str,
    ) -> None:
        """
        Explanation:
            Cash handed over beyond the bill, with no change mentioned
            ("paid with a 2,000 note" for a 1,050 bill), means the extra
            came back as change. Only for cash, and only when exactly one
            cash payment could have covered the extra: paying too much by
            card is usually a mistake or a tip, so that stays a problem.
            Adjusts `amounts` in place and says what it assumed.

        Parameters:
            amounts: Each payment's amount after stated change (or None).
            extracted: The extraction's payments, for the method.
            total: The expense's total.
            currency: For the note.
        """
        if not extracted or None in amounts:
            return

        surplus = sum((amount for amount in amounts if amount is not None), ZERO) - total

        if surplus <= 0:
            return

        candidates = [
            index
            for index, payment in enumerate(extracted)
            if payment.method == "cash"
            and payment.change is None
            and (amounts[index] or ZERO) > surplus
        ]

        if len(candidates) != 1:
            return

        index = candidates[0]
        handed = amounts[index] or ZERO
        amounts[index] = handed - surplus
        self.notes.append(
            f"Handed over {currency} {handed:,.2f} in cash, "
            f"so {currency} {surplus:,.2f} came back as change."
        )

    def fill_the_rest(
        self,
        stated: list[Decimal | None],
        total: Decimal,
        what: str,
    ) -> list[Decimal] | None:
        """
        Explanation:
            Complete a list of payments or shares where at most one amount
            wasn't stated: that one gets "the rest". The result must add up
            exactly to the total.

        Parameters:
            stated: Each entry's amount, or None where not stated.
            total: What they must add up to.
            what: "payments" or "shares", for the problem message.

        Returns:
            Every amount, or None (with a problem recorded) if that's impossible.
        """
        missing = [index for index, amount in enumerate(stated) if amount is None]
        known = sum((amount for amount in stated if amount is not None), ZERO)

        if len(missing) > 1:
            self.problems.append(
                f"How much was each of the {what}? I can only work out one missing amount."
            )
            return None

        amounts = list(stated)

        if missing:
            rest = total - known
            if rest <= 0:
                self.problems.append(
                    f"The {what} you gave already add up to {known}, but the total is {total}."
                )
                return None
            amounts[missing[0]] = rest
        elif known != total:
            self.problems.append(f"The {what} add up to {known}, but the total is {total}.")
            return None

        return [amount for amount in amounts if amount is not None]

    def total_said_final(self, extraction: ExpenseExtraction) -> bool:
        """
        True when the text says the total is what was paid: the model
        quoted words saying so, or the text says every tax, fee or
        discount is included ("including 18% GST", "GST included",
        "inclusive of tax"), which the model sometimes doesn't quote.
        """
        if self.stated(extraction.total_said_final):
            return True
        changes = [a for a in extraction.adjustments if a.amount is not None or a.percent is not None]
        if not changes:
            return False
        text = _normalize(self.text)
        for change in changes:
            names = [_normalize(adjustment_label(change))]
            if change.percent is not None:
                names.append(_normalize(change.percent.evidence))
            names = "|".join(re.escape(name) for name in names if name)
            if not names:
                return False
            # "including 18% GST", "incl. GST", "inclusive of tax", or
            # after it: "GST included", "18% GST inclusive".
            before = rf"\b(?:including|incl\.?|inclusive of)\s+(?:\S+\s+){{0,3}}?(?:{names})"
            after = rf"(?:{names})\W*(?:\S+\s+){{0,3}}?(?:included|inclusive|incl\.?)(?!\w)"
            if not re.search(before, text) and not re.search(after, text):
                return False
        return True

    def price_before_or_after(self, extraction: ExpenseExtraction) -> ExpenseExtraction:
        """
        The extraction with its one price taken as what was paid, or as the
        price before its discounts and taxes, as the user picked; asked
        while it isn't known. Only for a price read as the total with no
        words in the text saying so, when the bill has no items or price
        before the changes, and a change is stated in money or percent.
        """
        price = extraction.total
        changes = [a for a in extraction.adjustments if a.amount is not None or a.percent is not None]
        # Items named without any price ("1,180 for the course") are only
        # what was bought: the price is still the bill's one price.
        priced = [i for i in extraction.items if i.line_total is not None or i.unit_price is not None]
        if (
            price is None or extraction.subtotal is not None or priced or not changes
            or self.total_said_final(extraction)
        ):
            return extraction
        if "price_final" in self.decisions:
            return extraction.model_copy(update={"total": price, "subtotal": None})
        if "price_before" in self.decisions:
            return extraction.model_copy(update={"total": None, "subtotal": price, "items": []})

        what = joined([adjustment_label(a) for a in changes])
        said = price.evidence.strip()
        self.problems.append(f"Is {said} what you paid, or the price before the {what}?")
        self.choices.append(DraftChoice(decision="price_final", label=f"{said} is what I paid"))
        self.choices.append(DraftChoice(decision="price_before", label=f"{said} is before the {what}"))
        # Its answer prices whatever was named without a price: not asked too.
        return extraction.model_copy(update={"items": []})

    def ask_still_to_pay(
        self,
        unpaid: list[ExtractedPayment],
        stated: list[Decimal | None],
        total: Decimal,
        currency: str,
        unpaid_is_mine: bool,
    ) -> None:
        """
        Part of the bill is still to be paid, so the payments can't add up
        to it yet. Never counted as paid on its own: the user can save it
        once it's paid or, when it's theirs to pay, say to count it now.
        """
        paid = sum((amount for amount in stated if amount is not None), ZERO) if None not in stated else None
        so_far = f"Only {currency} {paid:,.2f} of the {currency} {total:,.2f} has been paid so far"
        if paid is None or paid >= total:
            so_far = "Part of it is still to be paid"

        if unpaid_is_mine:
            self.problems.append(f"{so_far}, and the rest is still to be paid. Save it once it's all paid?")
            self.choices.append(DraftChoice(decision="pay_later", label="Save it now as all paid by me"))
        else:
            names = self.who(list(dict.fromkeys(p.payer_ref for p in unpaid)))
            self.problems.append(f"{so_far}, and the rest is still to be paid by {names}. Save it once it's paid.")

    # the whole draft
    def build(self, extraction: ExpenseExtraction) -> ExpenseDraft:
        """
        Explanation:
            Turn one extraction into a draft, applying every rule in this
            module's docstring.

        Parameters:
            extraction: What the model extracted for one expense.

        Returns:
            The draft, with any problems listed.
        """
        # Change whose words aren't in the text wasn't said: it's the
        # model's own subtraction, so it's dropped and worked out from what
        # was handed over and the bill (infer_cash_change).
        if any(p.change is not None and not self.stated(p.change.evidence) for p in extraction.payments):
            extraction = extraction.model_copy(update={"payments": [
                p.model_copy(update={"change": None}) if p.change is not None and not self.stated(p.change.evidence)
                else p
                for p in extraction.payments
            ]})

        # A refund that's only promised hasn't come back: it changes
        # nothing yet, and the draft says so. Dropped before anyone is
        # looked up, so nobody is asked about only because of it.
        expected_refunds = [r for r in extraction.refunds if r.status == "expected"]
        if expected_refunds:
            extraction = extraction.model_copy(
                update={"refunds": [r for r in extraction.refunds if r.status != "expected"]}
            )
            for refund in expected_refunds:
                which = f" of “{refund.amount.evidence.strip()}”" if refund.amount else ""
                self.notes.append(
                    f"The refund{which} hasn't come back yet, so it isn't counted. "
                    "Add it to this expense once it does."
                )

        # One price and a stated discount or tax, with nothing else on the
        # bill ("Groceries 1,840, used a 200 coupon"): whether the price is
        # what was paid or before the change is read two ways, and they
        # differ by the change itself. Asked unless the user said.
        extraction = self.price_before_or_after(extraction)

        # A shop known only as "the store" can't be a contact, and who was
        # paid needs no question: its words stay in the description.
        paid_to_entity = next((e for e in extraction.entities if e.ref == extraction.merchant_ref), None)
        if paid_to_entity is not None and paid_to_entity.kind != "person" and not (paid_to_entity.name or "").strip():
            extraction = extraction.model_copy(update={"merchant_ref": None})

        self.resolve_entities(extraction.entities, used=refs_in(extraction))
        self.household = extraction.household and self.stated(extraction.household_evidence)
        # Whoever was paid never shares the cost.
        if extraction.merchant_ref:
            self.businesses.add(extraction.merchant_ref)
            self.organizations.discard(extraction.merchant_ref)

        currency = currency_of(extraction.currency, self.user.default_currency)

        # Money still to be paid isn't a payment. Only when the user says
        # so is what they still owe the shop counted as paid by them.
        unpaid = [p for p in extraction.payments if p.status == "expected"]
        unpaid_is_mine = bool(unpaid) and all(
            (person := self.person(p.payer_ref)) is not None and person.kind == "me" for p in unpaid
        )
        pay_later = unpaid_is_mine and "pay_later" in self.decisions
        still_to_pay = bool(unpaid) and not pay_later

        # What each payer actually paid: what they handed over, less any
        # change they got back. Worked out before the bill, because with
        # no total and nothing added or taken off, what was paid is the
        # total ("Coffee: gave 200, got 60 back" -> 140), and completes
        # an item with no price like a stated total does.
        extracted_payments = [p for p in extraction.payments if p.status == "happened" or pay_later]
        payers = [self.person(p.payer_ref) for p in extracted_payments] or [ME]
        self.payer_refs = [p.payer_ref for p in extracted_payments]
        stated, unreadable = self.net_payments(extracted_payments, currency)
        paid_total = (
            sum((amount for amount in stated if amount is not None), ZERO)
            if extracted_payments and not unreadable and None not in stated
            and not extraction.adjustments and extraction.subtotal is None and not still_to_pay
            else None
        )

        # The bill from its parts: items + charges - deductions.
        total = self.money(extraction.total, "total")
        total_known = extraction.total is not None or paid_total is not None
        before_bill = len(self.problems)
        # One item with no price, on a bill with percentages, and a total
        # said to be what was paid: the percentages and the total fix it.
        derived = (
            self.price_from_total(extraction, total)
            if total is not None and (self.total_said_final(extraction) or "price_final" in self.decisions)
            else None
        )
        bill = self.build_bill(extraction, total_stated=total_known, derived=derived)
        if derived:
            [(index, price)] = derived.items()
            self.notes.append(
                f"The {extraction.items[index].name} is what the {total:,.2f} leaves after "
                f"{joined([adjustment_label(a) for a in extraction.adjustments])}: {price:,.2f}."
            )

        # The final amount: as stated, else from the bill's parts, else
        # from what was paid ("Coffee: paid 500, got 380 back" -> 120).
        if total is None and extraction.total is None:
            # With taxes or discounts mentioned, the total must come from
            # the bill's parts; what was handed over can't stand in.
            total = bill.final if bill.final is not None else paid_total

        if total is not None and total <= 0:
            self.problems.append("What's taken off comes to the whole bill or more.")
            total = None

        if total is None and extraction.total is None and not self.problems:
            self.problems.append("How much was it? I couldn't find the amount.")

        if total is not None and total_known:
            self.complete_from_total(
                bill,
                total,
                listed_only=not extraction.adjustments and extraction.subtotal is None,
            )
        if bill.missing is not None and total is None:
            self.problems.append(f"What did the {bill.missing.name} cost?")

        # A stated total must agree with the parts that will be saved.
        # Other questions about the parts come first; a disagreement is
        # only asked about once every part is known.
        if total is not None:
            self.reconcile(bill, total)
            if bill.final is not None or len(self.problems) == before_bill:
                total = self.settle_total(bill, total) or total

        if bill.breakdown and not self.choices:
            self.notes.append(bill.breakdown)

        # Refunds: money given back after paying, each its own event. The
        # bill and its payments stay as paid; the cost that was shared is
        # what's left after them.
        refunds = self.refund_amounts(extraction)
        refunded = sum((amount for _, amount in refunds), ZERO)
        shared = total

        if total is not None and refunded >= total > 0:
            self.problems.append(
                f"The refunds come to {refunded:,.2f}, all of the {total:,.2f} or more."
            )
            shared = None

        # who shares the cost (first: payments can depend on it)
        participants: list[DraftShare] = []
        split = self.effective_split(extraction, bill)
        # The default rule is only for when nothing was said about whose it
        # is; a stated allocation that couldn't be checked stays a question.
        stated_allocation_failed = self.allocation_refused

        from_settlement = (
            self.shares_from_settlement(extraction, stated, shared)
            if split is None and shared is not None and not unreadable else None
        )

        # A group shared by more people than are named ("split among 4 of
        # us"): who owes what can't be known. Asked, or (one tap) only the
        # user's own even share is recorded.
        my_share_only: Decimal | None = None
        group = self.unnamed_group(split, shared)
        if group is not None:
            count, mine = group
            if "my_share_only" in self.decisions and mine is not None:
                my_share_only = mine
                self.notes.append(
                    f"Only your share is recorded: {currency} {mine:,.2f} of the {currency} {shared:,.2f} "
                    f"split {count} ways. The others aren't named, so what they owe isn't tracked."
                )
            else:
                self.problems.append(f"It's split between {count} people, but not everyone is named. "
                                     "Who are the others?")
                if mine is not None:
                    self.choices.append(DraftChoice(
                        decision="my_share_only", label=f"Just record my share ({currency} {mine:,.2f})"))

        if group is not None:
            participants = [DraftShare(person=ME, share_amount=shared)] if my_share_only is not None else []
        elif shared is not None:
            if from_settlement is not None:
                participants = from_settlement
            elif split is None and stated_allocation_failed:
                pass  # its problem is already recorded
            elif split is None and self.others:
                # Others are involved and nothing says whose cost this is:
                # being with someone isn't owning it, so it's asked, with
                # one-tap answers (never assumed, never "all yours").
                owners = self.ask_whose("this")
                if owners is not None:
                    split = ExtractedSplit(
                        method="equal", shares=[ExtractedShare(ref=ref) for ref in owners], evidence=[],
                    )
                    participants = self.split_shares(split, shared, bill)
            elif split is None:
                participants = [DraftShare(person=ME, share_amount=shared)]
                # Nobody else involved: every item can only be the user's.
                self.items_follow_split = True
            else:
                participants = self.split_shares(split, shared, bill)

        # who paid. Nobody said: a cost that's only yours is yours to have
        # paid; one shared with others needs to be told, since whoever
        # paid is owed by the rest.
        payments: list[DraftPayment] = []
        others_share = any(share.person.kind != "me" for share in participants)

        if total is not None and still_to_pay:
            self.ask_still_to_pay(unpaid, stated, total, currency, unpaid_is_mine)
        elif total is not None and not extracted_payments and others_share:
            self.problems.append("Who paid, and how much? You didn't say, and others share the cost.")
        elif total is not None:
            if not unreadable:
                self.infer_cash_change(stated, extracted_payments, total, currency)

            # A payer the user said paid exactly their own share ("I pay
            # 60% and Parth 40%") paid what their share works out to. Never
            # assumed: it must be said, in words that are in the text.
            share_of = {self.person_key(s.person): s.share_amount for s in participants}
            for index, (payment, payer) in enumerate(zip(extracted_payments, payers)):
                if payment.paid_own_share is None or stated[index] is not None:
                    continue
                if not self.stated(payment.paid_own_share):
                    self.problems.append("I couldn't find where you said who paid their own share.")
                    unreadable = True
                elif payer is None or self.person_key(payer) not in share_of:
                    name = payer.name if payer else "Someone"
                    self.problems.append(f"{name} paid their share, but I couldn't work out what it was.")
                    unreadable = True
                else:
                    stated[index] = share_of[self.person_key(payer)]

            # A stated payment that failed its check must not quietly
            # become "the rest".
            amounts = None if unreadable else self.fill_the_rest(stated, total, "payments")

            if amounts is not None:
                for index, (payer, amount) in enumerate(zip(payers, amounts)):
                    if payer is None:
                        continue
                    method = extracted_payments[index].method if extracted_payments else None
                    provider = extracted_payments[index].provider if extracted_payments else None
                    payments.append(
                        DraftPayment(person=payer, amount=amount, method=method, provider=provider)
                    )

        # Someone else paid for what's only the user's: that's owed back,
        # or their treat. Never assumed to be a debt: what the text says,
        # else asked with one tap.
        participants = self.owed_or_treat(extracted_payments, payments, participants)

        # A repayment in this message that settles what its payer owed must
        # agree with the shares: if it doesn't, the two readings are shown,
        # never one silently chosen.
        if from_settlement is None and participants and payments and shared is not None:
            participants = self.agree_with_settlement(extraction, stated, shared, participants, payments)

        # the rest of the fields
        date = self.date_of(extraction.date)

        # A cost that comes back is recorded one payment at a time, and
        # only a payment that was made: never saved as a one-off silently.
        # Its price alone ("Netflix 649 every month") is what it costs, not
        # a payment: one was made only when the text says who paid.
        if extraction.repeats != "no" and self.stated(extraction.repeats_evidence):
            how_often = REPEATS[extraction.repeats]
            paid = extraction.status == "happened" and bool(extraction.payments)
            if paid or "record_once" in self.decisions:
                self.notes.append(
                    f"This comes back {how_often}. Only this payment ({date:%d %b %Y}) is recorded; "
                    "tell me each time it's paid."
                )
            else:
                self.problems.append(
                    f"This comes back {how_often}, but what you wrote doesn't say a payment was made. "
                    f"Record one paid on {date:%d %b %Y}?"
                )
                self.choices.append(DraftChoice(decision="record_once", label="Yes, record one payment"))
        elif extraction.status != "happened":
            # Kept only as a repeating cost, which it can't be shown to be.
            self.problems.append("What you wrote doesn't say this was paid. Tell me once it has been.")

        # Who got each refund back: whoever the text says, as long as they
        # paid; else the one person who paid; with several payers, asked.
        recipients = self.refund_recipients(refunds, payments or payers, date, currency)
        draft_refunds = [refund for refund in recipients if refund is not None]

        # Nobody gets back more than they paid.
        paid_by: dict[tuple, Decimal] = {}
        for payment in payments:
            paid_by[identity(payment.person)] = paid_by.get(identity(payment.person), ZERO) + payment.amount
        back: dict[tuple, tuple[DraftPerson, Decimal]] = {}
        for refund in draft_refunds:
            key = identity(refund.person)
            back[key] = (refund.person, back.get(key, (refund.person, ZERO))[1] + refund.amount)
        for key, (person, amount) in back.items():
            if payments and amount > paid_by.get(key, ZERO):
                who = "You" if person.kind == "me" else person.name
                self.problems.append(
                    f"{who} got {currency} {amount:,.2f} back but paid {currency} {paid_by.get(key, ZERO):,.2f}. "
                    "Who got the refund?"
                )

        # Then whose share each refund comes off (not the same question).
        participants = self.apply_refunds(participants, refunds, recipients, bill, currency)


        category = extraction.category if extraction.category in CATEGORY_KEYS else DEFAULT_CATEGORY
        description = " ".join((extraction.description or "").split())[:255] or None

        paid_to = self.person(extraction.merchant_ref)
        if paid_to is not None and paid_to.kind == "me":
            paid_to = None

        # A shop that isn't in Merchants is never added on its own: one
        # tap adds it; otherwise its name stays in the description.
        if paid_to is not None and paid_to.kind == "new":
            decision = f"add_shop:0:{_normalize(paid_to.name)}"
            if decision in self.decisions:
                for contact in self.new_contacts:
                    if contact.key == paid_to.new_key:
                        contact.confirmed = True
            else:
                self.choices.append(DraftChoice(decision=decision, label=f"Add {paid_to.name} to Merchants"))
                if _normalize(paid_to.name) not in _normalize(description or ""):
                    description = f"{description or 'Paid'} at {paid_to.name}"[:255]
                paid_to = None

        # Only propose contacts the draft actually uses.
        used = {
            person.new_key
            for person in [
                paid_to,
                *(p.person for p in payments),
                *(s.person for s in participants),
                *(r.person for r in draft_refunds),
            ]
            if person is not None and person.kind == "new"
        }

        # Someone of the user's household who isn't in People and has no
        # part in the money (a household cost): offered with one tap,
        # never added on its own, and nothing waits on it.
        if self.household:
            for ref in sorted(self.others):
                person = self.people.get(ref)
                if person is None or person.kind != "new" or person.new_key in used:
                    continue
                decision = f"new_person:{_normalize(person.name)}"
                if decision in self.decisions:
                    used.add(person.new_key)
                elif all(choice.decision != decision for choice in self.choices):
                    label = self.called.get(ref, person.name)
                    self.choices.append(DraftChoice(decision=decision, label=f"Add {label} to People"))

        self.confirm_new_people(used)

        if my_share_only is not None:
            # Just the user's part, paid by them: the bill's lines are of
            # the whole, so they're left out.
            method = next((p.method for p in extracted_payments if self.person(p.payer_ref) is ME), None)
            return ExpenseDraft(
                excerpt=extraction.excerpt, date=date, amount=my_share_only, currency=currency,
                description=description, category=category, discount_amount=ZERO, items=[],
                paid_to=paid_to, payments=[DraftPayment(person=ME, amount=my_share_only, method=method)],
                participants=[DraftShare(person=ME, share_amount=my_share_only)],
                new_contacts=[c for c in self.new_contacts if paid_to is not None and c.key == paid_to.new_key],
                problems=list(dict.fromkeys(self.problems)), notes=list(dict.fromkeys(self.notes)),
                choices=self.choices,
            )

        return ExpenseDraft(
            item_owners=self.item_owners(bill) if participants else [],
            excerpt=extraction.excerpt,
            date=date,
            amount=total,
            currency=currency,
            description=description,
            category=category,
            discount_amount=bill.deducted,
            items=bill.items,
            charges=bill.charges,
            deductions=bill.deductions,
            refunds=draft_refunds,
            paid_to=paid_to,
            payments=payments,
            participants=participants,
            new_contacts=[c for c in self.new_contacts if c.key in used],
            # The same problem can come up twice (e.g. one unknown person
            # in both payments and shares); list it once.
            problems=list(dict.fromkeys(self.problems)),
            notes=list(dict.fromkeys(self.notes)),
            choices=self.choices,
        )


def build_drafts(
    extractions: list[ExpenseExtraction],
    text: str,
    user: User,
    contacts: list[Counterparty],
    today: dt.date,
) -> list[ExpenseDraft]:
    """
    Explanation:
        Build a draft for every extracted expense. Each gets a fresh
        Builder, so one expense's problems never leak into another's.

    Parameters:
        extractions: What the model extracted.
        text: What the user typed (the evidence must be in it).
        user: The signed-in user.
        contacts: The user's contacts, for matching names.
        today: The date used when none was stated.

    Returns:
        One draft per expense.
    """
    return [
        Builder(text=text, user=user, contacts=contacts, today=today).build(extraction)
        for extraction in extractions
    ]


# Why a part of a message wasn't recorded, in words for the user.
SKIPPED_REASONS = {
    "refund_of_earlier_purchase": (
        "is a refund for something bought earlier. Open that expense and add "
        "it there as a refund instead."
    ),
    "income": "is money coming in. TellSpend tracks spending and money between people.",
    "own_transfer": (
        "is your own money moving between your accounts, so nothing was spent. "
        "Record what you buy with it instead."
    ),
    "other": "isn't an expense or a repayment, so it wasn't recorded.",
}


def skipped_message(part: NotRecorded) -> str:
    return f"“{part.excerpt}” {SKIPPED_REASONS[part.kind]}"


class Facts:
    """
    Which words of the message can back a fact. Parts that tell the
    assistant what to do or record (the extraction's `instructions`) are
    not what happened: facts are checked against the rest of the text, and
    anything backed only by an instruction is dropped before a draft is
    built, whatever the model did with it.
    """

    def __init__(self, text: str, instructions: list[str]):
        self.full = _normalize(text)
        spans = [_normalize(span) for span in instructions if _normalize(span)]
        # Cut out, with a gap, so no evidence can run across the cut.
        facts = self.full
        for span in spans:
            facts = facts.replace(span, " \u2026 ")
        self.facts = facts
        self.instructions = " \u2026 ".join(spans)

    def only_instructed(self, words: str | list[str] | None) -> bool:
        """True if these words are in the message only inside an instruction."""
        phrases = [words] if isinstance(words, str) else list(words or [])
        phrases = [_normalize(phrase) for phrase in phrases if _normalize(phrase)]
        return any(phrase not in self.facts and phrase in self.full for phrase in phrases)

    def mentioned_only_in_instructions(self, entity: Entity) -> bool:
        names = [_normalize(word) for word in (entity.name, entity.relationship) if word and word.strip()]
        if not names or entity.ref == SELF_REF or entity.kind == "self":
            return False
        return not any(name in self.facts for name in names) and any(name in self.instructions for name in names)

    def keep_expense(self, e: ExpenseExtraction) -> ExpenseExtraction:
        """The expense without anything only an instruction backs."""
        gone = {entity.ref for entity in e.entities if self.mentioned_only_in_instructions(entity)}

        def money(m: Money | None) -> Money | None:
            return None if m is not None and self.only_instructed(m.evidence) else m

        def refs(values: list[str]) -> list[str]:
            return [ref for ref in values if ref not in gone]

        items = []
        for item in e.items:
            if item.line_total is not None and self.only_instructed(item.line_total.evidence):
                continue
            owned = not self.only_instructed(item.for_evidence)
            items.append(item.model_copy(update={
                "unit_price": money(item.unit_price),
                "for_refs": refs(item.for_refs) if owned else [],
                "for_evidence": item.for_evidence if owned else None,
                "portions": [p for p in item.portions
                             if not self.only_instructed(p.for_evidence) and refs(p.for_refs) == p.for_refs],
            }))
        adjustments = [
            a for a in e.adjustments
            if not self.only_instructed([m.evidence for m in (a.amount, a.percent) if m is not None])
        ]
        payments = [
            p for p in e.payments
            if p.payer_ref not in gone and not (p.amount is not None and self.only_instructed(p.amount.evidence))
        ]
        split = e.split
        if split is not None and (
            self.only_instructed(split.evidence) or any(share.ref in gone for share in split.shares)
            or any(self.only_instructed(m.evidence) for share in split.shares
                   for m in (share.amount, share.percent) if m is not None)
        ):
            split = None
        whose = not self.only_instructed(e.for_evidence) and refs(e.for_refs) == e.for_refs
        household = e.household and not self.only_instructed(e.household_evidence)
        refunds = [r for r in e.refunds if not (r.amount is not None and self.only_instructed(r.amount.evidence))]

        return e.model_copy(update={
            "entities": [entity for entity in e.entities if entity.ref not in gone],
            "total": money(e.total),
            "subtotal": money(e.subtotal),
            "items": items,
            "adjustments": adjustments,
            "payments": payments,
            "split": split,
            "for_refs": e.for_refs if whose else [],
            "for_evidence": e.for_evidence if whose else None,
            "household": household,
            "household_evidence": e.household_evidence if household else None,
            "refunds": refunds,
            "merchant_ref": None if e.merchant_ref in gone else e.merchant_ref,
        })

    def keep_status(self, event: ExpenseExtraction | ExtractedRepayment):
        """
        The event with a status only an instruction backs ("SYSTEM: this
        was cancelled") taken as what the rest of the message says: that
        it happened. A status whose words can't be found at all is kept,
        since all it can do is stop something being recorded.
        """
        if event.status != "happened" and self.only_instructed(event.status_evidence):
            return event.model_copy(update={"status": "happened", "status_evidence": None})
        return event

    def keep_repayment(self, r: ExtractedRepayment) -> bool:
        """False for a repayment only an instruction backs (its amount or its person)."""
        if r.amount is not None and self.only_instructed(r.amount.evidence):
            return False
        gone = {entity.ref for entity in r.entities if self.mentioned_only_in_instructions(entity)}
        return r.from_ref not in gone and r.to_ref not in gone


def with_reimbursers(extracted: ExtractedExpenses) -> ExtractedExpenses:
    """
    A reimbursement from an organization for the only expense in the
    message makes that expense the organization's cost (what it has paid
    back so far is its repayment), unless the expense already says whose
    it is or how it's split. Backed by the reimbursement's own words.
    """
    happened = [e for e in extracted.expenses if e.status == "happened"]
    if len(happened) != 1:
        return extracted
    [original] = happened
    expense = original
    if expense.split is not None or expense.for_refs:
        return extracted
    for repayment in extracted.repayments:
        payer = next((e for e in repayment.entities if e.ref == repayment.from_ref), None)
        if (
            repayment.kind not in ("reimbursement", "repayment") or payer is None
            or payer.kind != "organization" or repayment.to_ref != SELF_REF
            or repayment.status not in ("happened", "expected")
        ):
            continue
        same = next((e for e in expense.entities if e.kind == "organization"
                     and _normalize(e.name or "") == _normalize(payer.name or "")), None)
        ref = same.ref if same else "reimburser"
        entities = expense.entities if same else [*expense.entities, payer.model_copy(update={"ref": ref})]
        if repayment.status == "expected" and repayment.amount is not None:
            # A stated amount it will pay back is its share; the rest is
            # whoever else's the expense is (worked out, or asked).
            expense = expense.model_copy(update={"entities": entities, "split": ExtractedSplit(
                method="amounts", shares=[ExtractedShare(ref=ref, amount=repayment.amount)],
                evidence=[repayment.excerpt],
            )})
        else:
            expense = expense.model_copy(update={
                "entities": entities, "for_refs": [ref], "for_evidence": repayment.excerpt,
            })
        # What it has paid back is its reimbursement; a promise to pay is
        # nothing more than the cost being its own.
        reimbursement = repayment.model_copy(update={"kind": "reimbursement", "for_share": False})
        kept = [] if repayment.status == "expected" else [reimbursement]
        return extracted.model_copy(update={
            "expenses": [expense if e is original else e for e in extracted.expenses],
            "repayments": [r2 for r in extracted.repayments for r2 in (kept if r is repayment else [r])],
        })
    return extracted


# Why nothing was recorded for an event that didn't (yet) take place, in
# words for the user.
NOT_HAPPENED_REASONS = {
    "expected": "hasn't happened yet, so nothing was recorded. Tell me once it has.",
    "didnt_happen": "didn't happen, so nothing was recorded.",
    "hypothetical": "is a question or a what-if, not something that happened, so nothing was recorded.",
    "request": "asks for a reminder or a request, which isn't money that moved, so nothing was recorded.",
    "told_before": "is something you've told me about before, so it wasn't recorded again.",
    "owed": "is about money owed, not something bought, so it wasn't recorded as an expense.",
}


def only_what_happened(
    extracted: ExtractedExpenses,
) -> tuple[ExtractedExpenses, list[str], list[ExtractedRepayment]]:
    """
    Explanation:
        Keep only the events that took place, since only those change
        money; each one that didn't gets a message saying why it wasn't
        recorded. Decided here from each event's status, whatever else
        the model filled in.

        An existing debt ("owed") is money between people of kind
        "balance": no money moved, but the debt is real now. A repeating
        cost with no payment described is kept, so its draft can ask
        whether to record one payment (see Builder.build). Money between
        people that's only expected ("he'll pay me back next week") is
        returned on its own, so it can be remembered.

    Parameters:
        extracted: What the model extracted.

    Returns:
        (what happened, a message for everything else, expected money).
    """
    messages: list[str] = []

    def skip(excerpt: str, status: str) -> None:
        messages.append(f"“{excerpt.strip()}” {NOT_HAPPENED_REASONS[status]}")

    expenses = []
    for expense in extracted.expenses:
        standing = expense.repeats != "no" and expense.status == "expected"
        if expense.status == "happened" or standing:
            expenses.append(expense)
        else:
            skip(expense.excerpt, expense.status)

    repayments = []
    expected = []
    for repayment in extracted.repayments:
        if repayment.status == "owed" or (repayment.kind == "balance" and repayment.status == "happened"):
            repayments.append(repayment.model_copy(update={"kind": "balance", "status": "owed"}))
        elif repayment.status == "happened":
            repayments.append(repayment)
        elif repayment.status == "expected":
            expected.append(repayment)
        else:
            skip(repayment.excerpt, repayment.status)

    not_recorded = []
    for part in extracted.not_recorded:
        if part.status == "expected":
            messages.append(
                f"“{part.excerpt.strip()}” hasn't come in yet, so nothing was recorded. "
                "Once it has, add it to the expense it's for."
            )
        else:
            not_recorded.append(part)

    return extracted.model_copy(update={
        "expenses": expenses, "repayments": repayments, "not_recorded": not_recorded,
    }), messages, expected


# How often a repeating cost comes back, in words.
REPEATS = {
    "daily": "every day", "weekly": "every week", "monthly": "every month",
    "yearly": "every year", "other": "regularly",
}


# What money between the user and someone can be (see models.Settlement).
MONEY_KINDS = ("repayment", "loan", "reimbursement", "gift", "balance")


def joined(names: list[str]) -> str:
    """ "Parth", "Parth and Riya", "Parth, Riya and Meera" (each once)."""
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


def same_kind(entity: Entity, contact: Counterparty) -> bool:
    """A person is only ever a person contact; a shop or organization only one that isn't."""
    return (entity.kind == "person") == ((contact.counterparty_type or "PERSON") == "PERSON")


def unit_price_of(price: Decimal, count: Decimal, stated: Decimal | None, whole: bool) -> Decimal | None:
    """
    The price of one unit of a line or part: as stated when it fits, else
    when the price divides into it exactly. A whole line of one unit has
    no separate unit price to keep.
    """
    if stated is not None and abs(stated * count - price) <= PAISA * max(count, Decimal(1)):
        return stated
    if whole and count == 1:
        return None
    each = (price / count).quantize(PAISA, ROUND_HALF_UP)
    return each if each * count == price else None


def fully_refunded(draft: ExpenseDraft) -> bool:
    """True if everyone who paid got back exactly what they paid: all of it."""
    if draft.amount is None or not draft.refunds or not draft.payments:
        return False

    def per_person(rows) -> dict[tuple, Decimal]:
        totals: dict[tuple, Decimal] = {}
        for row in rows:
            totals[identity(row.person)] = totals.get(identity(row.person), ZERO) + row.amount
        return totals

    return sum((r.amount for r in draft.refunds), ZERO) == draft.amount and (
        per_person(draft.refunds) == per_person(draft.payments)
    )


def draft_balances(draft: ExpenseDraft) -> dict[tuple, Decimal]:
    """What a draft leaves owed between the user and each person, by identity() (positive: they owe the user)."""
    def key(person: DraftPerson):
        return None if person.kind == "me" else identity(person)

    return net_with_you(
        [(key(p.person), p.amount) for p in draft.payments],
        [(key(r.person), r.amount) for r in draft.refunds],
        [(key(s.person), s.share_amount) for s in draft.participants],
    )


def currency_of(raw: str | None, default: str) -> str:
    """A stated ISO currency code, else the user's own."""
    code = (raw or "").strip().upper()
    return code if len(code) == 3 and code.isalpha() else default


def refs_in(extraction: ExpenseExtraction) -> set[str]:
    """Every ref something in the expense refers to (payers, shares, owners, refunds, who was paid)."""
    refs = {SELF_REF, *extraction.for_refs, *(p.payer_ref for p in extraction.payments)}
    if extraction.split is not None:
        refs |= {share.ref for share in extraction.split.shares}
    for item in extraction.items:
        refs |= set(item.for_refs)
        for portion in item.portions:
            refs |= set(portion.for_refs)
    for adjustment in extraction.adjustments:
        refs |= set(adjustment.for_refs)
    for refund in extraction.refunds:
        refs |= set(refund.for_refs) | ({refund.to_ref} if refund.to_ref else set())
    if extraction.merchant_ref:
        refs.add(extraction.merchant_ref)
    return refs


def identity(person: DraftPerson) -> tuple:
    """
    Who a draft person is, the same across drafts of one message: new
    contacts' keys differ per draft, so they're known by name.
    """
    if person.kind == "me":
        return ("me",)
    if person.kind == "contact":
        return ("contact", person.contact_id)
    return ("new", person.name.casefold())


def build_result(
    extracted: ExtractedExpenses,
    text: str,
    user: User,
    contacts: list[Counterparty],
    today: dt.date,
    balances: dict[int, dict[str, Decimal]] | None = None,
    decisions: set[str] | None = None,
) -> AssistantPreviewResponse:
    """
    Explanation:
        Everything the message described, checked and worked out: a draft
        for each expense and each repayment, and a message for anything
        that can't be recorded. Each draft gets a fresh Builder, so one
        draft's problems never leak into another's.

    Parameters:
        extracted: What the model extracted.
        text: What the user typed (the evidence must be in it).
        user: The signed-in user.
        contacts: The user's contacts, for matching names.
        today: The date used when none was stated.
        balances: contact id -> balance in the user's currency, for
            "settled everything" repayments.
        decisions: Choices the user picked on the draft ("keep_total"...).

    Returns:
        The drafts and skipped parts.
    """

    # What the message tells the assistant to do is not what happened:
    # facts are checked against the rest, and what only an instruction
    # backs is dropped (and the instructions are listed back as ignored).
    # That includes whether something happened.
    facts = Facts(text, extracted.instructions)
    extracted = extracted.model_copy(update={
        "expenses": [facts.keep_status(e) for e in extracted.expenses],
        "repayments": [facts.keep_status(r) for r in extracted.repayments],
    })

    # An organization paying the user back for the one expense in the
    # message (in part or in full, or promising to) is who that cost
    # belongs to, unless the message allocated it otherwise.
    extracted = with_reimbursers(extracted)

    told = extracted.repayments

    # Only what happened changes money. Everything else is listed back,
    # with why nothing was recorded for it.
    extracted, not_happened, expected = only_what_happened(extracted)

    extracted = extracted.model_copy(update={
        "expenses": [facts.keep_expense(e) for e in extracted.expenses],
        "repayments": [r for r in extracted.repayments if facts.keep_repayment(r)],
    })
    # Only what the user typed is listed back: the model sometimes quotes
    # the app's own context (the date, the user's name) as an instruction
    # or a part it skipped, and that must never be shown as theirs.
    typed = _normalize(text)
    ignored = [
        f"“{span.strip()}” tells the assistant what to do rather than saying what happened, so it was ignored."
        for span in extracted.instructions if _normalize(span) and _normalize(span) in typed
    ]

    def builder(**extra) -> Builder:
        return Builder(text=facts.facts, user=user, contacts=contacts, today=today, **extra)

    # Who the user pays back, or says they will, in this message: whoever
    # paid for the user is then owed it (see Builder.owed_or_treat).
    repaid_to: set[tuple] = set()
    for repayment in (r for r in told if facts.keep_repayment(r)):
        if repayment.from_ref != SELF_REF or repayment.kind not in ("repayment", "reimbursement", "balance", "unclear"):
            continue
        reader = builder()
        reader.resolve_entities(repayment.entities)
        if (person := reader.people.get(repayment.to_ref)) is not None:
            repaid_to.add(identity(person))

    default = user.default_currency

    # Repayments that settle what their payer owed for an expense in this
    # message: (payer, receiver) -> (amount, currency, which repayment).
    settling: dict[tuple, tuple[Money, str, int]] = {}
    for index, repayment in enumerate(extracted.repayments):
        if not repayment.for_share or repayment.amount is None or repayment.kind not in ("repayment", "reimbursement"):
            continue
        reader = builder()
        reader.resolve_entities(repayment.entities)
        payer, receiver = reader.people.get(repayment.from_ref), reader.people.get(repayment.to_ref)
        if payer is not None and receiver is not None:
            settling[(identity(payer), identity(receiver))] = (
                repayment.amount, currency_of(repayment.currency, default), index)

    def people_of(expense: ExpenseExtraction) -> set[tuple]:
        reader = builder()
        reader.resolve_entities(expense.entities)
        return {identity(p) for p in reader.people.values() if p is not None}

    involved = [people_of(expense) for expense in extracted.expenses]
    # Which expense each settling repayment is for: the one expense both
    # people are part of (with several, it isn't known, and nothing is
    # derived from it).
    settles: dict[tuple, int] = {
        pair: at for pair in settling
        if len(matches := [at for at, people in enumerate(involved) if set(pair) <= people]) == 1
        for at in matches
    }
    expenses = [
        builder(
            decisions=decisions or set(),
            repaid_to=repaid_to,
            # Shares follow from a repayment only in the expense's own
            # currency; another currency is handled below.
            settled={
                pair: money for pair, (money, paid_in, _) in settling.items()
                if settles.get(pair) == at and paid_in == currency_of(expense.currency, default)
            },
            repaid_words={
                _normalize(r.amount.evidence) for r in extracted.repayments if r.amount is not None
            },
        ).build(expense)
        for at, expense in enumerate(extracted.expenses)
    ]

    # Each person's share of this message's expenses, and what they leave
    # owed between the user and each person, per currency.
    shares: dict[tuple, Decimal] = {}
    owed_here: dict[tuple, dict[str, Decimal]] = {}
    for draft in expenses:
        for share in draft.participants:
            key = identity(share.person)
            shares[key] = shares.get(key, ZERO) + share.share_amount
        for key, amount in draft_balances(draft).items():
            by_currency = owed_here.setdefault(key, {})
            by_currency[draft.currency] = by_currency.get(draft.currency, ZERO) + amount

    repayments = [
        builder(shares_in_message=shares, balances=balances or {}, message_balances=owed_here,
                decisions=decisions or set()).build_repayment(repayment, index)
        for index, repayment in enumerate(extracted.repayments)
    ]

    # A repayment in one currency settling what was owed in another ("he
    # paid me back ₹2,250 for his half" of an AED dinner) settles that debt:
    # it's recorded in the debt's currency, for what was owed, and what was
    # actually handed over is kept in a note. What was owed must be known.
    for pair, (money, paid_in, index) in settling.items():
        at = settles.get(pair)
        draft = expenses[at] if at is not None else None
        if draft is None or draft.currency == paid_in:
            continue
        repayment = repayments[index]
        share = sum((s.share_amount for s in draft.participants if identity(s.person) == pair[0]), ZERO)
        paid = sum((p.amount for p in draft.payments if identity(p.person) == pair[0]), ZERO)
        owed = share - paid
        if draft.participants and draft.payments and owed > 0 and repayment.amount is not None:
            repayments[index] = repayment.model_copy(update={
                "currency": draft.currency,
                "amount": owed,
                "notes": [*repayment.notes, f"Paid as {paid_in} {repayment.amount:,.2f}, settling the "
                                            f"{draft.currency} {owed:,.2f} owed for {draft.description or 'it'}."],
            })
        else:
            repayments[index] = repayment.model_copy(update={"problems": [
                *repayment.problems,
                f"This was paid in {paid_in}, but what it settles was in {draft.currency}. "
                f"How much {draft.currency} does it settle?",
            ]})

    # A repayment for someone's share of an expense in this message says
    # which one, so the two are saved linked.
    for index, repayment in enumerate(extracted.repayments):
        if not repayment.for_share:
            continue
        reader = builder()
        reader.resolve_entities(repayment.entities)
        payer, receiver = reader.people.get(repayment.from_ref), reader.people.get(repayment.to_ref)
        if payer is None or receiver is None:
            continue
        matches = [at for at, people in enumerate(involved) if {identity(payer), identity(receiver)} <= people]
        if len(matches) == 1:
            repayments[index] = repayments[index].model_copy(
                update={"settles_excerpt": expenses[matches[0]].excerpt})

    # Money that hasn't moved yet: nothing changes, but it can be remembered.
    expected_drafts = [builder(decisions=decisions or set()).build_expected(r) for r in expected]
    for draft, repayment in zip(expected_drafts, expected):
        if draft is None:
            not_happened.append(f"“{repayment.excerpt.strip()}” {NOT_HAPPENED_REASONS['expected']}")

    # Bought and given back in full, to whoever paid: it cost nothing, so
    # there's nothing to record (a refund can't be all of an expense).
    refunded_in_full = [draft for draft in expenses if fully_refunded(draft)]
    expenses = [draft for draft in expenses if draft not in refunded_in_full]
    not_happened += [
        f"“{draft.excerpt.strip()}” was refunded in full, so it cost nothing and nothing was recorded."
        for draft in refunded_in_full
    ]

    return AssistantPreviewResponse(
        expenses=expenses,
        repayments=repayments,
        expected=[draft for draft in expected_drafts if draft is not None],
        skipped=[*ignored, *not_happened, *(skipped_message(part) for part in extracted.not_recorded
                                            if _normalize(part.excerpt) in typed)],
    )
