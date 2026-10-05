import datetime as dt
from decimal import Decimal

import pytest

from tellspend.api import assistant
from tellspend.database.models import Counterparty, User
from tellspend.ingestion.builder import build_drafts, build_result, evidence_supports
from tellspend.ingestion.extraction import SELF_REF, ExpenseExtraction, ExtractedExpenses
from tellspend.ingestion.extractor import (
    EXAMPLES,
    FULL_EXAMPLES,
    KEY_REJECTED,
    NOT_SET_UP,
    OUT_OF_CREDITS,
    UNAVAILABLE,
    AssistantUnavailable,
    user_message_for,
)

ME = {"ref": SELF_REF, "kind": "self"}

def money(value, evidence=None):
    return {"value": value, "evidence": evidence or value}

def person(ref, name=None, relationship=None, kind="person"):
    return {"ref": ref, "kind": kind, "name": name, "relationship": relationship}

def extraction(text, **fields):
    return {"excerpt": text, "entities": [ME], **fields}

@pytest.fixture
def fake_model(monkeypatch):
    # Make the "model" return the given expenses (as dicts), and optionally
    # repayments and parts it can't record.
    def use(*extractions, repayments=(), not_recorded=()):
        def fake_extract(text, reference_date, user_name, turns=()):
            return ExtractedExpenses.model_validate({
                "expenses": list(extractions),
                "repayments": list(repayments),
                "not_recorded": list(not_recorded),
            })

        monkeypatch.setattr(assistant, "extract", fake_extract)

    return use

def preview(client, headers, text):
    return client.post("/assistant/preview", json={"text": text}, headers=headers)

def add_contact(client, headers, name, **fields):
    return client.post("/counterparties", json={"name": name, **fields}, headers=headers).json()["id"]

def contact_names(client, headers):
    return [c["name"] for c in client.get("/counterparties", headers=headers).json()]

def picked(client, headers, text, decisions):
    """The drafts again, with the choices the user tapped."""
    # As the app sends a tapped choice: its label as the answer, and the decision.
    turns = [{"asked": ["Is this someone new?"], "answer": "Yes"}]
    return client.post("/assistant/clarify", json={"text": text, "turns": turns, "decisions": decisions},
                       headers=headers).json()

# the worked examples in the prompt
@pytest.mark.parametrize(("text", "expenses"), EXAMPLES)
def test_prompt_examples_build_clean_balanced_drafts(text, expenses):
    # The prompt must never teach the model something the builder rejects.
    user = User(id=1, name="xyz", default_currency="INR")
    contacts = [
        Counterparty(id=1, name="Parth", counterparty_type="PERSON"),
        Counterparty(id=2, name="Riya", counterparty_type="PERSON"),
        Counterparty(id=3, name="Rahul", counterparty_type="PERSON"),
        Counterparty(id=4, name="Meera", counterparty_type="PERSON", relation="wife"),
        Counterparty(id=5, name="client", counterparty_type="ORGANIZATION"),
    ]

    drafts = build_drafts(
        [ExpenseExtraction.model_validate(e) for e in expenses],
        text,
        user,
        contacts,
        dt.date(2026, 9, 29),
    )

    for draft in drafts:
        assert draft.problems == []
        assert sum(p.amount for p in draft.payments) == draft.amount
        # Shares are of the cost left after any refunds.
        refunded = sum((r.amount for r in draft.refunds), Decimal("0"))
        assert sum(s.share_amount for s in draft.participants) == draft.amount - refunded

@pytest.mark.parametrize(("text", "parts"), FULL_EXAMPLES)
def test_full_prompt_examples_build_clean_drafts(text, parts):
    user = User(id=1, name="xyz", default_currency="INR")
    contacts = [Counterparty(id=3, name="Rahul", counterparty_type="PERSON"),
                Counterparty(id=4, name="Meera", counterparty_type="PERSON")]
    # What each contact owes the user, for examples that settle everything.
    balances = {4: {"INR": Decimal("650")}}

    result = build_result(ExtractedExpenses.model_validate(parts), text, user, contacts, dt.date(2026, 9, 29),
                          balances)

    for draft in [*result.expenses, *result.repayments]:
        assert draft.problems == []

# evidence
@pytest.mark.parametrize(
    ("value", "evidence", "supported"),
    [
        ("1200", "₹1,200", True),
        ("99.50", "Rs 99.50", True),
        ("120000", "1,20,000", True),
        # A word after the number scales it by a power of ten, in any
        # language, with no list of scale words.
        ("1200", "1.2k", True),
        ("200000", "2 lakh", True),
        ("3000000", "3 million", True),
        ("15000000", "1.5 crore", True),
        # Nothing scales a number without a word, or by anything else.
        ("12000", "1,200", False),
        ("1250", "1.2k", False),
        ("30", "3 kg", False),
        ("500", "five hundred", None),
    ],
)
def test_evidence_supports(value, evidence, supported):
    assert evidence_supports(Decimal(value), evidence) is supported

def test_simple_expense_is_all_yours(client, make_user, fake_model):
    headers = make_user()
    fake_model(extraction("Lunch 350", total=money("350"), description="Lunch", category="food_dining"))

    response = preview(client, headers, "Lunch 350")

    assert response.status_code == 200
    [draft] = response.json()["expenses"]
    assert draft["problems"] == []
    assert draft["amount"] == "350.00"
    assert draft["currency"] == "INR"
    assert draft["date"] == dt.date.today().isoformat()
    assert draft["category"] == "food_dining"
    assert draft["payments"][0]["person"]["kind"] == "me"
    assert draft["participants"][0]["share_amount"] == "350.00"

def test_scale_words_in_evidence_are_understood(client, make_user, fake_model):
    headers = make_user()
    fake_model(extraction("Laptop 1.2k", total=money("1200", "1.2k")))

    [draft] = preview(client, headers, "Laptop 1.2k").json()["expenses"]

    assert draft["problems"] == []
    assert draft["amount"] == "1200.00"

@pytest.mark.parametrize(
    "total",
    [
        money("1200", "1,200"), # evidence not in the text
        money("1200", "120"), # evidence says a different number
        money("-5", "-5") # not a valid amount
    ],
)
def test_numbers_not_backed_by_the_text_are_refused(client, make_user, fake_model, total):
    headers = make_user()
    fake_model(extraction("Lunch 120 -5", total=total))

    [draft] = preview(client, headers, "Lunch 120 -5").json()["expenses"]

    assert draft["amount"] is None
    assert draft["problems"]
    assert draft["payments"] == []


def test_missing_amount_is_a_problem(client, make_user, fake_model):
    headers = make_user()
    fake_model(extraction("Lunch with Parth"))

    [draft] = preview(client, headers, "Lunch with Parth").json()["expenses"]

    assert draft["amount"] is None
    assert any("How much" in p for p in draft["problems"])

# people
def test_split_equally_with_existing_contact(client, make_user, fake_model):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    fake_model(
        extraction(
            "Dinner 100 with parth, split, I paid",
            entities=[ME, person("e1", "parth")],
            total=money("100"),
            payments=[{"payer_ref": "me"}],
            split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}], "evidence": "split"},
        )
    )

    [draft] = preview(client, headers, "Dinner 100 with parth, split, I paid").json()["expenses"]

    assert draft["problems"] == []
    assert [s["share_amount"] for s in draft["participants"]] == ["50.00", "50.00"]
    assert draft["participants"][1]["person"] == {
        "kind": "contact", "contact_id": parth, "new_key": None, "name": "Parth",
    }
    assert draft["new_contacts"] == []


def test_equal_split_is_exact_to_the_paisa(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction(
            "100 for three",
            entities=[ME, person("e1", "A"), person("e2", "B")],
            total=money("100"),
            split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}, {"ref": "e2"}], "evidence": "for three"},
        )
    )

    [draft] = preview(client, headers, "100 for three").json()["expenses"]

    assert [s["share_amount"] for s in draft["participants"]] == ["33.34", "33.33", "33.33"]


def test_first_name_matches_a_unique_contact(client, make_user, fake_model):
    headers = make_user()
    parth = add_contact(client, headers, "Parth Shah")
    fake_model(
        extraction(
            "Parth paid 500",
            entities=[ME, person("e1", "Parth")],
            total=money("500"),
            payments=[{"payer_ref": "e1"}],
        )
    )

    [draft] = preview(client, headers, "Parth paid 500").json()["expenses"]

    assert draft["payments"][0]["person"]["contact_id"] == parth

def test_ambiguous_name_is_a_problem_not_a_guess(client, make_user, fake_model):
    headers = make_user()
    add_contact(client, headers, "Parth Shah")
    add_contact(client, headers, "Parth Mehta")
    fake_model(
        extraction(
            "Parth paid 500",
            entities=[ME, person("e1", "Parth")],
            total=money("500"),
            payments=[{"payer_ref": "e1"}],
        )
    )

    [draft] = preview(client, headers, "Parth paid 500").json()["expenses"]

    assert any("More than one" in p for p in draft["problems"])
    assert draft["new_contacts"] == []

def test_relationship_matches_contact_with_that_relation(client, make_user, fake_model):
    headers = make_user()
    meera = add_contact(client, headers, "Meera", relation="Wife")
    fake_model(
        extraction(
            "My wife paid 800 for my dinner, I owe her",
            entities=[ME, person("e1", relationship="wife")],
            total=money("800"),
            # Whether it's owed back is its own question (see test_scenarios).
            payments=[{"payer_ref": "e1", "owed_back": "owed", "owed_back_evidence": "I owe her"}],
            for_refs=["me"],
            for_evidence="my dinner",
        )
    )

    [draft] = preview(client, headers, "My wife paid 800 for my dinner, I owe her").json()["expenses"]

    assert draft["problems"] == []
    assert draft["payments"][0]["person"]["contact_id"] == meera

def test_unknown_relationship_without_name_is_proposed_as_a_new_contact(
    client, make_user, fake_model
):
    headers = make_user()
    said = extraction(
        "My wife paid 800 for my dinner, I owe her",
        entities=[ME, person("e1", relationship="wife")],
        total=money("800"),
        payments=[{"payer_ref": "e1", "owed_back": "owed", "owed_back_evidence": "I owe her"}],
        for_refs=["me"],
        for_evidence="my dinner",
    )
    fake_model(said)

    [asked] = preview(client, headers, "My wife paid 800 for my dinner, I owe her").json()["expenses"]

    # Nothing is lost: she's proposed under her relation, kept as payer,
    # and asked about before anyone is created.
    assert asked["problems"] == ["Your wife isn't in your People yet. Add them?"]
    assert asked["choices"] == [{"decision": "new_person:wife", "label": "Yes, add your wife"}]
    assert [(p["person"]["name"], p["amount"]) for p in asked["payments"]] == [("Wife", "800.00")]
    assert client.post("/assistant/confirm", json=asked, headers=headers).status_code == 422
    assert contact_names(client, headers) == []

    fake_model(said)
    [draft] = picked(client, headers, "My wife paid 800 for my dinner, I owe her", ["new_person:wife"])["expenses"]
    assert draft["problems"] == []
    assert draft["new_contacts"] == [
        {"key": "new1", "name": "Wife", "counterparty_type": "PERSON", "relation": "wife", "confirmed": True}
    ]
    assert client.post("/assistant/confirm", json=draft, headers=headers).status_code == 201

    # Next time "my wife" is the contact that was just created.
    fake_model(said)
    [again] = preview(client, headers, "My wife paid 800").json()["expenses"]
    assert again["new_contacts"] == []
    assert again["payments"][0]["person"]["kind"] == "contact"


def test_two_new_people_with_the_same_relation_get_different_names(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction(
            "Pizza 900 split equally with two friends",
            entities=[ME, person("e1", relationship="friend"), person("e2", relationship="friend")],
            total=money("900"),
            split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}, {"ref": "e2"}], "evidence": "split equally"},
        )
    )

    [draft] = preview(client, headers, "Pizza 900 split equally with two friends").json()["expenses"]

    assert [c["name"] for c in draft["new_contacts"]] == ["Friend", "Friend 2"]
    assert [s["share_amount"] for s in draft["participants"]] == ["300.00"] * 3


def test_unknown_names_become_proposed_contacts_once(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction(
            "Riya paid 900 at Cafe Zen, split with Riya",
            entities=[ME, person("e1", "Riya"), person("e2", "Cafe Zen", kind="business")],
            total=money("900"),
            merchant_ref="e2",
            payments=[{"payer_ref": "e1"}],
            split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}], "evidence": "split with Riya"},
        )
    )

    [draft] = preview(client, headers, "Riya paid 900 at Cafe Zen, split with Riya").json()["expenses"]

    # The person is asked about; the new shop is only offered (one tap),
    # never added on its own, and its name is kept in the description.
    assert draft["problems"] == ["Riya isn't in your People. Is Riya someone new?"]
    assert [(c["name"], c["counterparty_type"]) for c in draft["new_contacts"]] == [("Riya", "PERSON")]
    assert draft["paid_to"] is None
    assert {"decision": "add_shop:0:cafe zen", "label": "Add Cafe Zen to Merchants"} in draft["choices"]
    assert "Cafe Zen" in draft["description"]
    # Nothing is created until the draft is confirmed.
    assert contact_names(client, headers) == []

# payments and shares
def test_the_rest_of_a_split_payment(client, make_user, fake_model):
    headers = make_user()
    add_contact(client, headers, "Meera", relation="wife")
    text = "Cab 1200: my wife paid 500 cash, I paid the rest by HDFC card"
    fake_model(
        extraction(
            text,
            entities=[ME, person("e1", relationship="wife")],
            total=money("1200"),
            payments=[
                {"payer_ref": "e1", "amount": money("500"), "method": "cash"},
                {"payer_ref": "me", "method": "credit_card", "provider": "HDFC"},
            ],
        )
    )

    [draft] = preview(client, headers, text).json()["expenses"]

    assert [(p["amount"], p["method"], p["provider"]) for p in draft["payments"]] == [
        ("500.00", "cash", None),
        ("700.00", "credit_card", "HDFC"),
    ]

def test_more_than_one_unknown_payment_is_a_problem(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction(
            "Bill 1200, A and I paid",
            entities=[ME, person("e1", "A")],
            total=money("1200"),
            payments=[{"payer_ref": "e1"}, {"payer_ref": "me"}],
        )
    )

    [draft] = preview(client, headers, "Bill 1200, A and I paid").json()["expenses"]

    assert any("each" in p for p in draft["problems"])

def test_stated_shares_that_dont_add_up_are_a_problem(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction(
            "Pizza 600, my share 250, Rahul 300",
            entities=[ME, person("e1", "Rahul")],
            total=money("600"),
            split={
                "method": "amounts",
                "shares": [{"ref": "me", "amount": money("250")}, {"ref": "e1", "amount": money("300")}],
                "evidence": "my share 250, Rahul 300",
            },
        )
    )

    [draft] = preview(client, headers, "Pizza 600, my share 250, Rahul 300").json()["expenses"]

    assert any("add up to 550" in p for p in draft["problems"])

def test_a_share_that_fails_its_check_is_not_given_the_rest(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction(
            "Pizza 600 with Rahul",
            entities=[ME, person("e1", "Rahul")],
            total=money("600"),
            split={
                "method": "amounts",
                "shares": [{"ref": "me", "amount": money("250")}, {"ref": "e1"}],
                "evidence": "Pizza 600 with Rahul",
            },
        )
    )

    [draft] = preview(client, headers, "Pizza 600 with Rahul").json()["expenses"]

    assert draft["participants"] == []
    assert draft["problems"]

def test_items_and_discount_give_the_amount(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction(
            "rice 600, 2 kg apples 400, 50 off",
            items=[
                {"name": "rice", "line_total": money("600")},
                {"name": "apples", "quantity": "2", "unit": "kg", "line_total": money("400")},
            ],
            adjustments=[{"kind": "discount", "effect": "subtracts", "amount": money("50", "50 off")}],
        )
    )

    [draft] = preview(client, headers, "rice 600, 2 kg apples 400, 50 off").json()["expenses"]

    assert draft["problems"] == []
    assert draft["amount"] == "950.00"
    assert draft["discount_amount"] == "50.00"
    assert [i["name"] for i in draft["items"]] == ["rice", "apples"]

def test_taxes_and_fees_are_charges_not_items_through_to_saving(client, make_user, fake_model):
    headers = make_user()
    text = "lamp 900, fan 600, 100 off, GST 5%, delivery 40, paid 2000 cash"
    fake_model(
        extraction(
            text,
            items=[
                {"name": "lamp", "line_total": money("900")},
                {"name": "fan", "line_total": money("600")},
            ],
            adjustments=[
                {"kind": "discount", "effect": "subtracts", "amount": money("100", "100 off")},
                {"kind": "tax", "effect": "adds", "label": "GST", "percent": money("5", "5%")},
                {"kind": "delivery", "effect": "adds", "amount": money("40")},
            ],
            payments=[{"payer_ref": "me", "amount": money("2000"), "method": "cash"}],
        )
    )

    [draft] = preview(client, headers, text).json()["expenses"]

    # 1,500 - 100 + 40 delivery, then 5% GST on 1,440 = 72.
    assert draft["problems"] == []
    assert draft["amount"] == "1512.00"
    assert [i["name"] for i in draft["items"]] == ["lamp", "fan"]
    assert draft["charges"] == [
        {"kind": "delivery", "label": "Delivery", "amount": "40.00"},
        {"kind": "tax", "label": "GST", "amount": "72.00"},
    ]
    # Cash handed over: the change is worked out from the final amount.
    assert [p["amount"] for p in draft["payments"]] == ["1512.00"]

    saved = client.post("/assistant/confirm", json=draft, headers=headers)

    assert saved.status_code == 201
    assert [i["name"] for i in saved.json()["items"]] == ["lamp", "fan"]
    assert saved.json()["charges"] == draft["charges"]
    assert saved.json()["original_amount"] == "1612.00"

def test_several_expenses_get_separate_drafts_and_problems(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction("Tea 20", total=money("20")),
        extraction("Cab for too much", total=money("999")),
    )

    first, second = preview(client, headers, "Tea 20. Cab for too much").json()["expenses"]

    assert first["problems"] == []
    assert second["problems"]

def test_stated_date_and_currency_are_used_and_bad_ones_fall_back(client, make_user, fake_model):
    headers = make_user(default_currency="INR")
    fake_model(
        extraction("Hotel $80", total=money("80", "$80"), currency="usd", date="2026-09-20"),
        extraction("Tea 20", total=money("20"), currency="rupees", date="not a date"),
    )

    first, second = preview(client, headers, "Hotel $80. Tea 20").json()["expenses"]

    assert (first["currency"], first["date"]) == ("USD", "2026-09-20")
    assert (second["currency"], second["date"]) == ("INR", dt.date.today().isoformat())

# errors
def test_preview_needs_login_and_text(client, make_user, fake_model):
    fake_model()

    assert client.post("/assistant/preview", json={"text": "Lunch 350"}).status_code == 401
    assert preview(client, make_user(), "   ").status_code == 422

def test_unavailable_model_is_a_503_with_a_plain_message(client, make_user, monkeypatch):
    def broken(text, reference_date, user_name, turns=()):
        raise AssistantUnavailable(NOT_SET_UP)

    monkeypatch.setattr(assistant, "extract", broken)

    response = preview(client, make_user(), "Lunch 350")

    assert response.status_code == 503
    assert response.json()["detail"] == NOT_SET_UP

class ProviderError(Exception):
    """Stands in for an HTTP error from the AI provider's client library."""

    def __init__(self, status_code, message=""):
        super().__init__(message)
        self.status_code = status_code

def wrapped(inner):
    # LangChain re-raises the provider's error with it as the cause
    try:
        raise RuntimeError("wrapper") from inner
    except RuntimeError as outer:
        return outer

@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ProviderError(401, "API key expired"), KEY_REJECTED),
        (wrapped(ProviderError(401, "API key expired")), KEY_REJECTED),
        (ProviderError(403, "Forbidden"), KEY_REJECTED),
        (ProviderError(403, "Key limit exceeded"), OUT_OF_CREDITS),
        (ProviderError(403, "Workspace daily budget of $1.00 exceeded."), OUT_OF_CREDITS),
        (wrapped(ProviderError(403, "Insufficient credits")), OUT_OF_CREDITS),
        (ProviderError(429, "Monthly spend cap reached"), OUT_OF_CREDITS),
        (ProviderError(429, "Rate limit exceeded, slow down"), UNAVAILABLE),
        (ProviderError(403, "Invalid API key"), KEY_REJECTED),
        (ProviderError(402, "Payment required"), OUT_OF_CREDITS),
        (wrapped(ProviderError(429, "insufficient_quota")), OUT_OF_CREDITS),
        (ProviderError(500, "Server error"), UNAVAILABLE),
        (TimeoutError("timed out"), UNAVAILABLE),
    ],
)
def test_provider_errors_get_a_message_that_says_what_to_do(error, message):
    assert user_message_for(error) == message

# confirming a draft
def test_confirming_a_preview_saves_it_with_its_new_contacts(client, make_user, fake_model):
    headers = make_user()
    fake_model(
        extraction(
            "Riya paid 900, split with Riya",
            entities=[ME, person("e1", "Riya")],
            total=money("900"),
            payments=[{"payer_ref": "e1", "method": "upi"}],
            split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}], "evidence": "split with Riya"},
        )
    )
    [draft] = picked(client, headers, "Riya paid 900, split with Riya", ["new_person:riya"])["expenses"]

    # The draft is sent back exactly as it was returned.
    response = client.post("/assistant/confirm", json=draft, headers=headers)

    assert response.status_code == 201
    assert contact_names(client, headers) == ["Riya"]  # created once, used twice
    riya = client.get("/counterparties", headers=headers).json()[0]["id"]
    assert response.json()["payments"][0]["counterparty_id"] == riya
    assert response.json()["payments"][0]["method"] == "upi"
    assert client.get("/balances", headers=headers).json()[0]["amount"] == "-450.00"

def draft_body(**fields):
    me = {"kind": "me", "name": "You"}
    return {
        "date": "2026-09-01",
        "amount": "900",
        "payments": [{"person": me, "amount": "900"}],
        "participants": [{"person": me, "share_amount": "900"}],
        **fields,
    }

def test_confirm_that_does_not_add_up_saves_nothing(client, make_user):
    headers = make_user()
    new = {"kind": "new", "new_key": "new1", "name": "Riya"}

    response = client.post(
        "/assistant/confirm",
        json=draft_body(
            participants=[{"person": new, "share_amount": "100"}],
            new_contacts=[{"key": "new1", "name": "Riya", "confirmed": True}],
        ),
        headers=headers,
    )

    assert response.status_code == 422
    assert "Shares add up to" in response.json()["detail"][0]["msg"]
    assert contact_names(client, headers) == []

def test_confirm_with_someone_elses_contact_saves_nothing(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    theirs = add_contact(client, other, "Their Parth")
    new = {"kind": "new", "new_key": "new1", "name": "Riya"}

    response = client.post(
        "/assistant/confirm",
        json=draft_body(
            paid_to={"kind": "contact", "contact_id": theirs, "name": "Their Parth"},
            payments=[{"person": new, "amount": "900"}],
            new_contacts=[{"key": "new1", "name": "Riya", "confirmed": True}],
        ),
        headers=me,
    )

    assert response.status_code == 404
    assert contact_names(client, me) == []
    assert client.get("/expenses", headers=me).json() == []

def test_a_new_person_the_user_didnt_confirm_is_never_created(client, make_user):
    headers = make_user()
    new = {"kind": "new", "new_key": "new1", "name": "Kabir"}

    response = client.post(
        "/assistant/confirm",
        json=draft_body(
            participants=[{"person": {"kind": "me", "name": "You"}, "share_amount": "450"},
                          {"person": new, "share_amount": "450"}],
            new_contacts=[{"key": "new1", "name": "Kabir"}],
        ),
        headers=headers,
    )

    assert response.status_code == 422
    assert "Kabir isn't in your People" in response.json()["detail"]
    assert contact_names(client, headers) == []
    assert client.get("/expenses", headers=headers).json() == []


def test_confirm_with_unknown_new_contact_key_is_422(client, make_user):
    headers = make_user()

    response = client.post(
        "/assistant/confirm",
        json=draft_body(payments=[{"person": {"kind": "new", "new_key": "x", "name": "X"}, "amount": "900"}]),
        headers=headers,
    )

    assert response.status_code == 422

def test_a_new_contact_named_like_an_existing_one_in_another_case_reuses_it(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    new = {"kind": "new", "new_key": "new1", "name": "  parth "}

    response = client.post(
        "/assistant/confirm",
        json=draft_body(
            payments=[{"person": new, "amount": "900"}],
            new_contacts=[{"key": "new1", "name": "  parth "}],
        ),
        headers=headers,
    )

    assert response.status_code == 201, response.json()
    assert contact_names(client, headers) == ["Parth"]
    assert response.json()["payments"][0]["counterparty_id"] == parth
