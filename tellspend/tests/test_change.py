"""
Tests for cash handed over and change given back, in the assistant's
builder: what someone paid is what they handed over, less any change.

Each test gives the builder what the model would extract (no AI call), so
these cover every phrasing that reaches the same fields: stated change,
change with or without a total or items, change implied by overpaying in
cash, and the cases that must stay problems instead of being guessed.
"""

import datetime as dt
from decimal import Decimal

from tellspend.database.models import Counterparty, User
from tellspend.ingestion.builder import build_drafts
from tellspend.ingestion.extraction import SELF_REF, ExpenseExtraction


ME = {"ref": SELF_REF, "kind": "self"}
USER = User(id=1, name="xyz", default_currency="INR")
PARTH = {"ref": "e1", "kind": "person", "name": "Parth"}

# A neutral bill whose items come to 500.
ITEMS = [
    {"name": "notebook", "line_total": {"value": "240", "evidence": "240"}},
    {"name": "pens", "line_total": {"value": "90", "evidence": "90"}},
    {"name": "stapler", "line_total": {"value": "170", "evidence": "170"}},
]
ITEMS_TEXT = "notebook 240, pens 90, stapler 170."


def money(value, evidence=None):
    return {"value": value, "evidence": evidence or value}


def pay(amount=None, change=None, method=None, payer="me"):
    payment = {"payer_ref": payer, "method": method}
    if amount:
        payment["amount"] = money(amount)
    if change:
        payment["change"] = money(change)
    return payment


def build(text, **fields):
    """Build one draft from an extraction, as the preview route would."""
    extraction = ExpenseExtraction.model_validate({"excerpt": text, "entities": [ME], **fields})
    contacts = [Counterparty(id=7, name="Parth", counterparty_type="PERSON")]
    [draft] = build_drafts([extraction], text, USER, contacts, dt.date(2026, 9, 29))
    return draft


def paid(draft):
    return [(p.amount, p.method) for p in draft.payments]


# ---------- stated change ----------


def test_items_with_cash_and_change_is_the_bill_not_a_mismatch():
    draft = build(
        f"{ITEMS_TEXT} Handed over 600 cash and got 100 back.",
        items=ITEMS,
        payments=[pay("600", "100", "cash")],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("500.00")
    assert paid(draft) == [(Decimal("500.00"), "cash")]
    assert draft.notes == ["Handed over INR 600.00, INR 100.00 back as change."]


def test_stated_total_with_change():
    draft = build(
        "Bill 1050, gave 1100, received 50 change",
        total=money("1050"),
        payments=[pay("1100", "50")],
    )

    assert draft.problems == []
    assert paid(draft) == [(Decimal("1050.00"), None)]


def test_no_total_and_no_items_the_payment_after_change_is_the_total():
    draft = build("Coffee, paid 500 and got 380 back", payments=[pay("500", "380")])

    assert draft.problems == []
    assert draft.amount == Decimal("120.00")
    assert draft.participants[0].share_amount == Decimal("120.00")


def test_change_on_one_of_two_payers():
    draft = build(
        "My cab 1050: Parth paid 500 cash, I gave 1000 and got 450 back",
        entities=[ME, PARTH],
        for_refs=["me"],
        for_evidence="My cab",
        total=money("1050"),
        payments=[pay("500", method="cash", payer="e1"), pay("1000", "450")],
    )

    assert draft.problems == []
    assert [p.amount for p in draft.payments] == [Decimal("500.00"), Decimal("550.00")]


def test_change_then_equal_split_uses_the_real_bill():
    draft = build(
        f"{ITEMS_TEXT} Paid 600, got 100 back, split with Parth",
        entities=[ME, PARTH],
        items=ITEMS,
        payments=[pay("600", "100")],
        split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}], "evidence": "split with Parth"},
    )

    assert draft.problems == []
    assert [s.share_amount for s in draft.participants] == [Decimal("250.00"), Decimal("250.00")]


# ---------- change implied by overpaying in cash ----------


def test_paying_with_a_big_note_implies_change():
    draft = build(
        "Bill 1,050, paid with a 2,000 note",
        total=money("1050", "1,050"),
        payments=[{"payer_ref": "me", "amount": money("2000", "2,000"), "method": "cash"}],
    )

    assert draft.problems == []
    assert paid(draft) == [(Decimal("1050.00"), "cash")]
    assert draft.notes == ["Handed over INR 2,000.00 in cash, so INR 950.00 came back as change."]


def test_overpaying_in_cash_with_items_implies_change():
    draft = build(f"{ITEMS_TEXT} Gave 800 in cash.", items=ITEMS, payments=[pay("800", method="cash")])

    assert draft.problems == []
    assert draft.amount == Decimal("500.00")
    assert paid(draft) == [(Decimal("500.00"), "cash")]


# ---------- what must stay a problem ----------


def test_overpaying_by_card_is_not_assumed_to_be_change():
    draft = build("Dinner 1050, paid 1100 by card", total=money("1050"), payments=[pay("1100", method="card")])

    assert any("add up to 1100.00" in p for p in draft.problems)


def test_overpaying_with_no_method_is_not_assumed_to_be_change():
    draft = build("Dinner 1050, I paid 1100", total=money("1050"), payments=[pay("1100")])

    assert draft.problems


def test_two_cash_payers_who_both_could_have_got_change_is_not_guessed():
    draft = build(
        "Bill 1000, Parth gave 600 cash and I gave 600 cash",
        entities=[ME, PARTH],
        total=money("1000"),
        payments=[pay("600", method="cash", payer="e1"), pay("600", method="cash")],
    )

    assert draft.problems
    # Nothing about change is assumed.
    assert not any("change" in note for note in draft.notes)


def test_numbers_that_really_dont_match_stay_a_problem_with_the_change_shown():
    # Items come to 500, but 450 handed over with 50 back is 400 paid.
    draft = build(
        f"{ITEMS_TEXT} Paid 450 cash and got 50 back.",
        items=ITEMS,
        payments=[pay("450", "50", "cash")],
    )

    assert draft.problems == ["The payments add up to 400.00, but the total is 500.00."]
    assert draft.notes == ["Handed over INR 450.00, INR 50.00 back as change."]


def test_change_more_than_handed_over_is_a_problem():
    draft = build("Paid 100, got 150 back, bill 50", total=money("50"), payments=[pay("100", "150")])

    assert any("more than what was handed over" in p for p in draft.problems)
    assert draft.payments == []


def test_change_without_the_amount_handed_over_is_a_problem():
    draft = build("Lunch 300, got 200 back", total=money("300"), payments=[pay(change="200")])

    assert any("how much did you hand over" in p for p in draft.problems)
    assert draft.payments == []


def test_change_not_in_the_text_is_never_the_models_number():
    # The model's own subtraction isn't a stated fact: it's dropped. Not
    # cash, so nothing explains paying more than the bill: asked.
    draft = build("Lunch 300, paid 500", total=money("300"), payments=[pay("500", "200")])

    assert draft.problems == ["The payments add up to 500.00, but the total is 300.00."]
    assert draft.payments == []


def test_change_not_in_the_text_is_worked_out_for_cash():
    draft = build("Coffee 180, paid with a 500 note", total=money("180"),
                  payments=[pay("500", "320", method="cash")])

    assert draft.problems == []
    assert paid(draft) == [(Decimal("180.00"), "cash")]
    assert draft.notes == ["Handed over INR 500.00 in cash, so INR 320.00 came back as change."]
