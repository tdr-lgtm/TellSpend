"""Tests for balances (who owes whom) and settlements."""

from decimal import Decimal

import pytest

from tellspend.services.money import allocate


def add_contact(client, headers, name):
    return client.post("/counterparties", json={"name": name}, headers=headers).json()["id"]


def add_expense(client, headers, amount, payments=None, participants=None, **fields):
    body = {"date": "2026-09-01", "amount": amount, **fields}
    if payments is not None:
        body["payments"] = payments
    if participants is not None:
        body["participants"] = participants
    response = client.post("/expenses", json=body, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()


def balances(client, headers):
    """contact name -> (currency, amount) for every non-zero balance."""
    return {
        b["name"]: (b["currency"], b["amount"])
        for b in client.get("/balances", headers=headers).json()
    }


def pay(counterparty_id, amount):
    return {"counterparty_id": counterparty_id, "amount": amount}


def share(counterparty_id, amount):
    return {"counterparty_id": counterparty_id, "share_amount": amount}


def settle(client, headers, counterparty_id, direction, amount, **fields):
    return client.post(
        "/settlements",
        json={
            "counterparty_id": counterparty_id,
            "direction": direction,
            "amount": amount,
            "date": "2026-09-02",
            **fields,
        },
        headers=headers,
    )


# ---------- allocate ----------


@pytest.mark.parametrize(
    ("total", "weights", "expected"),
    [
        ("100", ["1", "1", "1"], ["33.34", "33.33", "33.33"]),
        ("10", ["1", "3"], ["2.50", "7.50"]),
        ("0.01", ["1", "1"], ["0.01", "0.00"]),
        ("1000", ["500", "500"], ["500.00", "500.00"]),
    ],
)
def test_allocate_splits_exactly(total, weights, expected):
    parts = allocate(Decimal(total), [Decimal(w) for w in weights])

    assert [str(p) for p in parts] == expected
    assert sum(parts) == Decimal(total)


# ---------- balances from expenses ----------


def test_personal_expenses_create_no_balances(client, make_user):
    headers = make_user()
    add_expense(client, headers, "500")

    assert client.get("/balances", headers=headers).json() == []


def test_you_paid_and_split_means_they_owe_you_their_share(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")

    add_expense(client, headers, "900", participants=[share(None, "450"), share(parth, "450")])

    assert balances(client, headers) == {"Parth": ("INR", "450.00")}


def test_contact_paid_for_you_means_you_owe_them(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")

    add_expense(client, headers, "1200", payments=[pay(parth, "1200")])

    assert balances(client, headers) == {"Parth": ("INR", "-1200.00")}


def test_money_between_two_contacts_is_not_your_balance(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    riya = add_contact(client, headers, "Riya")

    # Parth paid 900 for the three of you: you owe Parth 300. What Riya
    # owes Parth is between them.
    add_expense(
        client,
        headers,
        "900",
        payments=[pay(parth, "900")],
        participants=[share(None, "300"), share(parth, "300"), share(riya, "300")],
    )

    assert balances(client, headers) == {"Parth": ("INR", "-300.00")}


def test_two_payers_only_the_difference_counts(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")

    # You paid 700, Parth 500; each owes 600: Parth owes you 100.
    add_expense(
        client,
        headers,
        "1200",
        payments=[pay(None, "700"), pay(parth, "500")],
        participants=[share(None, "600"), share(parth, "600")],
    )

    assert balances(client, headers) == {"Parth": ("INR", "100.00")}


def test_debt_is_split_between_creditors_in_proportion(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    riya = add_contact(client, headers, "Riya")

    # You and Riya each paid 500 of Parth's 1000 dinner (you had none):
    # Parth owes each of you 500.
    add_expense(
        client,
        headers,
        "1000",
        payments=[pay(None, "500"), pay(riya, "500")],
        participants=[share(parth, "1000")],
    )

    assert balances(client, headers) == {"Parth": ("INR", "500.00")}


def test_balances_add_up_across_expenses_and_net_out(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")

    add_expense(client, headers, "900", participants=[share(None, "450"), share(parth, "450")])
    add_expense(client, headers, "200", payments=[pay(parth, "200")])

    assert balances(client, headers) == {"Parth": ("INR", "250.00")}


def test_currencies_are_kept_apart(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")

    add_expense(client, headers, "100", participants=[share(None, "50"), share(parth, "50")])
    add_expense(
        client,
        headers,
        "20",
        currency="USD",
        participants=[share(None, "10"), share(parth, "10")],
    )

    listed = client.get("/balances", headers=headers).json()

    assert sorted((b["currency"], b["amount"]) for b in listed) == [
        ("INR", "50.00"),
        ("USD", "10.00"),
    ]


def test_balances_only_show_your_own_expenses(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    their_parth = add_contact(client, other, "Parth")
    add_expense(client, other, "900", participants=[share(None, "450"), share(their_parth, "450")])

    assert client.get("/balances", headers=me).json() == []


# ---------- settlements ----------


def test_they_paid_me_back_clears_the_balance(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    add_expense(client, headers, "900", participants=[share(None, "450"), share(parth, "450")])

    response = settle(client, headers, parth, "they_paid_me", "450")

    assert response.status_code == 201
    assert response.json()["currency"] == "INR"
    assert client.get("/balances", headers=headers).json() == []


def test_i_paid_them_reduces_what_you_owe(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    add_expense(client, headers, "1200", payments=[pay(parth, "1200")])

    settle(client, headers, parth, "i_paid_them", "1000")

    assert balances(client, headers) == {"Parth": ("INR", "-200.00")}


def test_paying_back_too_much_flips_the_balance(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    add_expense(client, headers, "900", participants=[share(None, "450"), share(parth, "450")])

    settle(client, headers, parth, "they_paid_me", "500")

    assert balances(client, headers) == {"Parth": ("INR", "-50.00")}


def test_settlement_only_affects_its_currency(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    add_expense(client, headers, "900", participants=[share(None, "450"), share(parth, "450")])

    settle(client, headers, parth, "they_paid_me", "10", currency="usd")

    listed = client.get("/balances", headers=headers).json()
    assert sorted((b["currency"], b["amount"]) for b in listed) == [
        ("INR", "450.00"),
        ("USD", "-10.00"),
    ]


@pytest.mark.parametrize(
    "bad_fields",
    [
        {"direction": "sideways"},
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "1.001"},
        {"currency": "RUPEES"},
    ],
)
def test_settlement_rejects_bad_input(client, make_user, bad_fields):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")

    response = client.post(
        "/settlements",
        json={
            "counterparty_id": parth,
            "direction": "they_paid_me",
            "amount": "100",
            "date": "2026-09-02",
            **bad_fields,
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_settlement_with_someone_elses_contact_is_404(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    theirs = add_contact(client, other, "Parth")

    assert settle(client, me, theirs, "they_paid_me", "100").status_code == 404


def test_settlements_list_newest_first_and_only_own(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    parth = add_contact(client, me, "Parth")
    their_parth = add_contact(client, other, "Parth")

    older = settle(client, me, parth, "they_paid_me", "10", date="2026-08-01").json()
    newer = settle(client, me, parth, "i_paid_them", "20", date="2026-09-05").json()
    settle(client, other, their_parth, "they_paid_me", "30")

    listed = client.get("/settlements", headers=me).json()

    assert [s["id"] for s in listed] == [newer["id"], older["id"]]


def test_deleting_a_settlement_restores_the_balance(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    add_expense(client, headers, "900", participants=[share(None, "450"), share(parth, "450")])
    settlement = settle(client, headers, parth, "they_paid_me", "450").json()

    assert client.delete(f"/settlements/{settlement['id']}", headers=headers).status_code == 204
    assert balances(client, headers) == {"Parth": ("INR", "450.00")}


def test_cannot_delete_someone_elses_settlement(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    their_parth = add_contact(client, other, "Parth")
    theirs = settle(client, other, their_parth, "they_paid_me", "30").json()

    assert client.delete(f"/settlements/{theirs['id']}", headers=me).status_code == 404
    assert len(client.get("/settlements", headers=other).json()) == 1


def test_contact_with_settlements_cannot_be_deleted(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    settle(client, headers, parth, "they_paid_me", "30")

    response = client.delete(f"/counterparties/{parth}", headers=headers)

    assert response.status_code == 409
    assert "settlements" in response.json()["detail"]


def test_balances_and_settlements_require_login(client):
    assert client.get("/balances").status_code == 401
    assert client.get("/settlements").status_code == 401
