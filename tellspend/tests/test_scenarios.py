"""
Tests for scenarios across the app that used to go wrong: unnamed shops
and groups, names that are almost a contact's, who an even split is with,
what's owed in the same message, someone else paying for you, full and
oversized refunds, notes, linked repayments, expected money, contacts,
the summary, the profile, limits and logins. The model is replaced by
fixed extractions; everything here is the server's own logic.
"""

import datetime as dt
from decimal import Decimal

import pytest

from tellspend.api import assistant
from tellspend.database.models import Counterparty, User
from tellspend.ingestion.builder import build_result
from tellspend.ingestion.extraction import SELF_REF, ExtractedExpenses
from tellspend.services import rate_limit

ME = {"ref": SELF_REF, "kind": "self"}
PARTH = {"ref": "e1", "kind": "person", "name": "Parth"}
RIYA = {"ref": "e2", "kind": "person", "name": "Riya"}
USER = User(id=1, name="xyz", default_currency="INR")
CONTACTS = [
    Counterparty(id=7, name="Parth", counterparty_type="PERSON"),
    Counterparty(id=9, name="Riya", counterparty_type="PERSON"),
    Counterparty(id=20, name="Zara Khan", counterparty_type="PERSON"),
]
TODAY = dt.date(2026, 9, 29)


def money(value, evidence=None):
    return {"value": value, "evidence": evidence or value}


def run(text, expenses=(), repayments=(), balances=None, decisions=None):
    extracted = ExtractedExpenses.model_validate({
        "expenses": [{"excerpt": text, "entities": [ME], **e} for e in expenses],
        "repayments": [{"excerpt": text, **r} for r in repayments],
    })
    return build_result(extracted, text, USER, CONTACTS, TODAY, balances, decisions)


def shares(draft):
    return {s.person.name: s.share_amount for s in draft.participants}


@pytest.fixture
def fake_model(monkeypatch):
    def use(extracted: dict):
        monkeypatch.setattr(assistant, "extract",
                            lambda *args, **kwargs: ExtractedExpenses.model_validate(extracted))
    return use


# 1. a shop known only as "the store"
def test_a_shop_with_no_name_asks_nothing():
    text = "Shirt 2000 at the store"
    [draft] = run(text, expenses=[{
        "entities": [ME, {"ref": "e1", "kind": "business"}], "merchant_ref": "e1", "total": money("2000"),
    }]).expenses

    assert draft.problems == [] and draft.paid_to is None


# 2. a group with a count but no names
def test_a_group_with_no_names_asks_or_records_only_your_share():
    text = "Dinner 2000, split among 4 of us, I paid"
    expense = {"total": money("2000"), "payments": [{"payer_ref": SELF_REF}],
               "split": {"method": "equal", "shares": [{"ref": SELF_REF}], "evidence": "split among 4 of us",
                         "people_count": money("4", "4 of us")}}

    [asked] = run(text, expenses=[expense]).expenses
    assert "split between 4 people" in asked.problems[0]
    assert [c.decision for c in asked.choices] == ["my_share_only"]

    [mine] = run(text, expenses=[expense], decisions={"my_share_only"}).expenses
    assert mine.problems == [] and mine.amount == Decimal("500.00")
    assert shares(mine) == {"You": Decimal("500.00")}


# 3. a longer name than a contact's
def test_a_longer_name_asks_if_it_is_the_contact():
    text = "Lunch 600 with Parth Shah, split equally, I paid"
    expense = {"entities": [ME, {"ref": "e1", "kind": "person", "name": "Parth Shah"}], "total": money("600"),
               "payments": [{"payer_ref": SELF_REF}],
               "split": {"method": "equal", "shares": [{"ref": SELF_REF}, {"ref": "e1"}], "evidence": "split equally"}}

    [asked] = run(text, expenses=[expense]).expenses
    assert asked.problems[0] == "Is Parth Shah your contact Parth?"

    [same] = run(text, expenses=[expense], decisions={"same_person:parth shah"}).expenses
    assert same.problems == [] and shares(same) == {"You": Decimal("300.00"), "Parth": Decimal("300.00")}


# 4. a shop sharing a first name with a person
def test_a_shop_never_matches_a_person_by_first_name():
    text = "Shirt 1500 at Zara"
    [draft] = run(text, expenses=[{
        "entities": [ME, {"ref": "e1", "kind": "business", "name": "Zara"}], "merchant_ref": "e1",
        "total": money("1500"),
    }]).expenses

    assert draft.paid_to is None or draft.paid_to.kind != "contact"


# 6. an even split nobody was named for
def test_an_even_split_with_several_people_mentioned_asks_who_with():
    text = "Riya and I split the cab 300 equally, Parth drove, I paid"
    expense = {"entities": [ME, PARTH, RIYA], "total": money("300"), "payments": [{"payer_ref": SELF_REF}],
               "split": {"method": "equal", "shares": [{"ref": SELF_REF}], "evidence": "split the cab 300 equally"}}

    [asked] = run(text, expenses=[expense]).expenses
    assert asked.problems[0].startswith("Who is it split equally with?")

    [picked] = run(text, expenses=[expense], decisions={"split_with:riya"}).expenses
    assert shares(picked) == {"You": Decimal("150.00"), "Riya": Decimal("150.00")}


# 7. settling everything, in the same message
def test_settling_up_counts_what_this_message_adds():
    text = "Dinner 1200 with Parth, I paid, split equally. Parth settled up."
    result = run(
        text,
        expenses=[{"entities": [ME, PARTH], "total": money("1200"), "payments": [{"payer_ref": SELF_REF}],
                   "split": {"method": "equal", "shares": [{"ref": SELF_REF}, {"ref": "e1"}],
                             "evidence": "split equally"}}],
        repayments=[{"entities": [ME, PARTH], "kind": "repayment", "from_ref": "e1", "to_ref": SELF_REF,
                     "amount_source": "everything_owed"}],
        balances={7: {"INR": Decimal("100.00")}},
    )

    [repayment] = result.repayments
    assert repayment.problems == [] and repayment.amount == Decimal("700.00")


# 8. "her share", less what she already paid
def test_their_share_is_what_they_still_owe():
    text = "Dinner 1200 split equally with Parth, Parth paid 200 and I paid the rest, he sent me his share"
    result = run(
        text,
        expenses=[{"entities": [ME, PARTH], "total": money("1200"),
                   "payments": [{"payer_ref": "e1", "amount": money("200")}, {"payer_ref": SELF_REF}],
                   "split": {"method": "equal", "shares": [{"ref": SELF_REF}, {"ref": "e1"}],
                             "evidence": "split equally"}}],
        repayments=[{"entities": [ME, PARTH], "kind": "repayment", "from_ref": "e1", "to_ref": SELF_REF,
                     "amount_source": "their_share", "for_share": True}],
    )

    [repayment] = result.repayments
    assert repayment.amount == Decimal("400.00")
    assert repayment.settles_excerpt == text


# 9-10. someone else paying for what's yours
def test_someone_paying_for_you_asks_owed_or_treat():
    text = "Parth paid 500 for my movie ticket"
    expense = {"entities": [ME, PARTH], "total": money("500"), "payments": [{"payer_ref": "e1"}],
               "for_refs": [SELF_REF], "for_evidence": "my movie ticket"}

    [asked] = run(text, expenses=[expense]).expenses
    assert "Do you owe it back?" in asked.problems[0]
    assert [c.decision for c in asked.choices] == ["owe_payer", "treat"]

    [treat] = run(text, expenses=[expense], decisions={"treat"}).expenses
    assert treat.problems == [] and shares(treat) == {"Parth": Decimal("500.00")}

    [owed] = run(text, expenses=[expense], decisions={"owe_payer"}).expenses
    assert owed.problems == [] and shares(owed) == {"You": Decimal("500.00")}


def test_saying_its_a_treat_or_owed_asks_nothing():
    text = "Parth paid 500 for my ticket, his treat"
    expense = {"entities": [ME, PARTH], "total": money("500"),
               "payments": [{"payer_ref": "e1", "owed_back": "treat", "owed_back_evidence": "his treat"}],
               "for_refs": [SELF_REF], "for_evidence": "my ticket"}

    [draft] = run(text, expenses=[expense]).expenses
    assert draft.problems == [] and shares(draft) == {"Parth": Decimal("500.00")}


def test_paying_them_back_in_the_same_message_means_it_was_owed():
    text = "Parth paid 500 for my ticket, I'll pay him back tomorrow"
    result = run(
        text,
        expenses=[{"entities": [ME, PARTH], "total": money("500"), "payments": [{"payer_ref": "e1"}],
                   "for_refs": [SELF_REF], "for_evidence": "my ticket"}],
        repayments=[{"entities": [ME, PARTH], "kind": "repayment", "from_ref": SELF_REF, "to_ref": "e1",
                     "amount": money("500"), "status": "expected", "status_evidence": "tomorrow"}],
    )

    [draft] = result.expenses
    assert draft.problems == [] and shares(draft) == {"You": Decimal("500.00")}
    assert len(result.expected) == 1


# 18. given back in full
def test_a_purchase_refunded_in_full_records_nothing():
    text = "Bought a shirt 2000, returned it, got 2000 back"
    result = run(text, expenses=[{"total": money("2000"), "payments": [{"payer_ref": SELF_REF}],
                                  "refunds": [{"amount": money("2000"), "to_ref": SELF_REF}]}])

    assert result.expenses == []
    assert "refunded in full" in result.skipped[0]


# 19. more back than paid (on saving)
def test_saving_a_refund_bigger_than_what_was_paid_is_refused(client, make_user):
    headers = make_user()
    parth = client.post("/counterparties", json={"name": "Parth"}, headers=headers).json()["id"]
    response = client.post("/expenses", json={
        "date": "2026-09-01", "amount": "1000",
        "payments": [{"counterparty_id": None, "amount": "500"}, {"counterparty_id": parth, "amount": "500"}],
        "refunds": [{"counterparty_id": parth, "amount": "800"}],
    }, headers=headers)

    assert response.status_code == 422
    assert "more back than they paid" in str(response.json())


# 15 + 22. notes kept; an expense and its repayment saved linked
def test_notes_are_saved_and_a_repayment_links_to_its_expense(client, make_user):
    headers = make_user()
    parth = client.post("/counterparties", json={"name": "Parth"}, headers=headers).json()["id"]
    me = {"kind": "me", "name": "You"}
    them = {"kind": "contact", "contact_id": parth, "name": "Parth"}
    expense = client.post("/assistant/confirm", json={
        "date": "2026-09-01", "amount": "600", "payments": [{"person": me, "amount": "600"}],
        "participants": [{"person": me, "share_amount": "300"}, {"person": them, "share_amount": "300"}],
        "notes": ["The total 600.00 is an estimate."],
    }, headers=headers).json()
    assert expense["note"] == "The total 600.00 is an estimate."

    settlement = client.post("/assistant/confirm-repayment", json={
        "date": "2026-09-01", "amount": "300", "kind": "repayment", "from_person": them, "to_person": me,
        "expense_id": expense["id"],
    }, headers=headers).json()
    assert settlement["expense_id"] == expense["id"]
    [listed] = client.get("/expenses", headers=headers).json()
    assert listed["settlement_ids"] == [settlement["id"]]

    # Deleting it with its repayment leaves nothing owed either way.
    assert client.delete(f"/expenses/{expense['id']}?with_settlements=true", headers=headers).status_code == 204
    assert client.get("/settlements", headers=headers).json() == []
    assert client.get("/balances", headers=headers).json() == []


# 11. expected money: remembered, then it happens
def test_expected_money_is_remembered_and_becomes_a_payment(client, make_user):
    headers = make_user()
    parth = client.post("/counterparties", json={"name": "Parth"}, headers=headers).json()["id"]
    them = {"kind": "contact", "contact_id": parth, "name": "Parth"}
    saved = client.post("/assistant/confirm-expected", json={
        "from_person": them, "to_person": {"kind": "me", "name": "You"}, "amount": "500",
        "due_date": "2026-10-08", "note": "he'll return it next week",
    }, headers=headers)
    assert saved.status_code == 201
    # Nothing owed changes while it's expected.
    assert client.get("/balances", headers=headers).json() == []

    [expected] = client.get("/expected", headers=headers).json()
    done = client.post(f"/expected/{expected['id']}/done", json={"date": "2026-10-08"}, headers=headers)
    assert done.status_code == 201 and done.json()["direction"] == "they_paid_me"
    assert client.get("/expected", headers=headers).json() == []
    [balance] = client.get("/balances", headers=headers).json()
    assert balance["amount"] == "-500.00"


# 12. a card re-read whole, only its own part back
def test_answering_one_card_reads_the_whole_message_and_returns_only_that_part(client, make_user, fake_model):
    headers = make_user()
    text = "Lunch 350. Auto 80"
    fake_model({"expenses": [
        {"excerpt": "Lunch 350", "entities": [ME], "total": money("350"), "description": "Lunch"},
        {"excerpt": "Auto 80", "entities": [ME], "total": money("80"), "description": "Auto"},
    ]})

    result = client.post("/assistant/clarify", json={
        "text": text, "focus": "Auto 80", "turns": [{"asked": ["?"], "answer": "by cash"}],
    }, headers=headers).json()
    assert [d["excerpt"] for d in result["expenses"]] == ["Auto 80"]


# 5. one name, one contact
def test_a_second_contact_with_the_same_name_is_refused(client, make_user):
    headers = make_user()
    assert client.post("/counterparties", json={"name": "Parth"}, headers=headers).status_code == 201
    response = client.post("/counterparties", json={"name": " parth "}, headers=headers)
    assert response.status_code == 409


# 20. a shop can't have a share
def test_a_shop_with_a_share_is_refused(client, make_user):
    headers = make_user()
    shop = client.post("/counterparties", json={"name": "Zepto", "counterparty_type": "BUSINESS"},
                       headers=headers).json()["id"]
    response = client.post("/expenses", json={
        "date": "2026-09-01", "amount": "100",
        "participants": [{"counterparty_id": shop, "share_amount": "100"}],
    }, headers=headers)
    assert response.status_code == 422


# 21. an item's owner must share the cost
def test_an_item_owner_without_a_share_is_refused(client, make_user):
    headers = make_user()
    parth = client.post("/counterparties", json={"name": "Parth"}, headers=headers).json()["id"]
    response = client.post("/expenses", json={
        "date": "2026-09-01", "amount": "100",
        "items": [{"name": "Pizza", "amount": "100", "owners": [{"counterparty_id": parth, "amount": "100"}]}],
    }, headers=headers)
    assert response.status_code == 422


# 23. only money between you and one person can be turned into it
def test_a_shared_expense_cant_become_a_repayment(client, make_user):
    headers = make_user()
    parth = client.post("/counterparties", json={"name": "Parth"}, headers=headers).json()["id"]
    riya = client.post("/counterparties", json={"name": "Riya"}, headers=headers).json()["id"]
    expense = client.post("/expenses", json={
        "date": "2026-09-01", "amount": "900",
        "participants": [{"counterparty_id": None, "share_amount": "300"},
                         {"counterparty_id": parth, "share_amount": "300"},
                         {"counterparty_id": riya, "share_amount": "300"}],
    }, headers=headers).json()

    response = client.post(f"/expenses/{expense['id']}/to-settlement",
                           json={"counterparty_id": parth, "direction": "i_paid_them"}, headers=headers)
    assert response.status_code == 422


# 24-26. the month's numbers
def test_the_summary_counts_refunds_when_they_come_and_gifts_as_spending(client, make_user):
    headers = make_user()
    riya = client.post("/counterparties", json={"name": "Riya"}, headers=headers).json()["id"]
    client.post("/expenses", json={
        "date": "2026-08-20", "amount": "1000", "category": "shopping",
        "refunds": [{"amount": "200", "date": "2026-09-05"}],
    }, headers=headers)
    client.post("/settlements", json={"counterparty_id": riya, "direction": "i_paid_them", "kind": "gift",
                                      "amount": "500", "date": "2026-09-10"}, headers=headers)

    [inr] = client.get("/summary?month=2026-09", headers=headers).json()["currencies"]
    assert inr["your_spending"] == "500.00"
    assert inr["you_paid"] == "300.00"  # 500 given, 200 back
    assert inr["by_category"] == [{"category": "gifts_donations", "amount": "500.00"}]


# 28. the profile
def test_the_profile_can_be_changed_and_the_account_deleted(client, make_user):
    headers = make_user()
    changed = client.patch("/users/me", json={"name": "xyz", "default_currency": "usd"}, headers=headers).json()
    assert (changed["name"], changed["default_currency"]) == ("xyz", "USD")

    client.post("/counterparties", json={"name": "Parth"}, headers=headers)
    assert client.request("DELETE", "/users/me", json={"password": "wrong"}, headers=headers).status_code == 403
    assert client.request("DELETE", "/users/me", json={"password": "secret123"}, headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


# 29. how often the assistant can be asked
def test_the_assistant_refuses_past_its_limit(monkeypatch):
    from fastapi import HTTPException
    from tellspend.database.config import settings

    rate_limit.reset()
    monkeypatch.setattr(settings, "assistant_requests_per_minute", 2)
    rate_limit.check_assistant_limit(99, now=1000.0)
    rate_limit.check_assistant_limit(99, now=1001.0)
    with pytest.raises(HTTPException) as refused:
        rate_limit.check_assistant_limit(99, now=1002.0)
    assert refused.value.status_code == 429
    # A minute later it's fine again.
    rate_limit.check_assistant_limit(99, now=1070.0)
    rate_limit.reset()


# 30. a login from before a password change, even the same second
def test_a_token_from_before_a_password_change_stops_working(client, make_user, db):
    headers = make_user()
    me = client.get("/auth/me", headers=headers).json()
    user = db.get(User, me["id"])
    # Changed within the same second the token was made.
    user.password_changed_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    assert client.get("/auth/me", headers=headers).status_code == 401
