"""Tests for who paid, who shares the cost, and "paid to" on expenses."""

import pytest


DINNER = {"date": "2026-09-01", "amount": "1200", "description": "Dinner"}


def add_contact(client, headers, name="Parth", **fields):
    """Create a contact and return its id."""
    response = client.post("/counterparties", json={"name": name, **fields}, headers=headers)
    return response.json()["id"]


def create(client, headers, **fields):
    """Create an expense and return the response."""
    return client.post("/expenses", json={**DINNER, **fields}, headers=headers)


def expense_count(client, headers):
    return len(client.get("/expenses", headers=headers).json())


def who_paid(body):
    """The payments without method/provider: who paid, and how much."""
    return [{"counterparty_id": p["counterparty_id"], "amount": p["amount"]} for p in body["payments"]]


# ---------- defaults ----------


def test_without_payments_or_shares_you_paid_all_and_it_is_all_yours(client, make_user):
    headers = make_user()

    body = create(client, headers).json()

    assert body["counterparty_id"] is None
    assert who_paid(body) == [{"counterparty_id": None, "amount": "1200.00"}]
    assert body["participants"] == [{"counterparty_id": None, "share_amount": "1200.00"}]


# ---------- recording who paid and who shares ----------


def test_split_three_ways_that_you_paid(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers, "Parth")
    riya = add_contact(client, headers, "Riya")

    response = create(
        client,
        headers,
        amount="100",
        participants=[
            {"counterparty_id": None, "share_amount": "33.34"},
            {"counterparty_id": parth, "share_amount": "33.33"},
            {"counterparty_id": riya, "share_amount": "33.33"},
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert who_paid(body) == [{"counterparty_id": None, "amount": "100.00"}]
    assert [p["counterparty_id"] for p in body["participants"]] == [None, parth, riya]


def test_contact_paid_and_it_was_only_yours(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    body = create(client, headers, payments=[{"counterparty_id": parth, "amount": "1200"}]).json()

    assert who_paid(body) == [{"counterparty_id": parth, "amount": "1200.00"}]
    assert body["participants"] == [{"counterparty_id": None, "share_amount": "1200.00"}]


def test_two_payers(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    response = create(
        client,
        headers,
        payments=[
            {"counterparty_id": None, "amount": "700"},
            {"counterparty_id": parth, "amount": "500"},
        ],
    )

    assert response.status_code == 201
    assert [p["amount"] for p in response.json()["payments"]] == ["700.00", "500.00"]


def test_paid_to_contact(client, make_user):
    headers = make_user()
    swiggy = add_contact(client, headers, "Swiggy", counterparty_type="BUSINESS")

    assert create(client, headers, counterparty_id=swiggy).json()["counterparty_id"] == swiggy


# ---------- rules ----------


@pytest.mark.parametrize(
    "bad_fields",
    [
        # Totals must match the amount exactly.
        {"payments": [{"amount": "1000"}]},
        {"payments": [{"amount": "1300"}]},
        {"participants": [{"share_amount": "1199.99"}]},
        # Empty lists are not "left out".
        {"payments": []},
        {"participants": []},
        # Nobody twice.
        {"participants": [{"share_amount": "600"}, {"counterparty_id": None, "share_amount": "600"}]},
        # Amounts must be positive with at most 2 decimals.
        {"participants": [{"share_amount": "1200.001"}]},
        {"payments": [{"amount": "0"}, {"counterparty_id": 1, "amount": "1200"}]},
    ],
)
def test_rejects_bad_payments_and_shares(client, make_user, bad_fields):
    headers = make_user()

    assert create(client, headers, **bad_fields).status_code == 422


def test_rejects_same_contact_twice(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    response = create(
        client,
        headers,
        participants=[
            {"counterparty_id": parth, "share_amount": "600"},
            {"counterparty_id": parth, "share_amount": "600"},
        ],
    )

    assert response.status_code == 422


@pytest.mark.parametrize("where", ["counterparty_id", "payments", "participants"])
def test_someone_elses_contact_is_404_and_nothing_is_saved(client, make_user, where):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    theirs = add_contact(client, other, "Their Parth")

    fields = {
        "counterparty_id": {"counterparty_id": theirs},
        "payments": {"payments": [{"counterparty_id": theirs, "amount": "1200"}]},
        "participants": {"participants": [{"counterparty_id": theirs, "share_amount": "1200"}]},
    }[where]

    response = create(client, me, **fields)

    assert response.status_code == 404
    assert expense_count(client, me) == 0


def test_unknown_contact_is_404(client, make_user):
    headers = make_user()

    assert create(client, headers, counterparty_id=999999).status_code == 404


# ---------- editing ----------


def test_edit_replaces_payments_and_shares_even_with_the_same_people(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)
    split = [
        {"counterparty_id": None, "share_amount": "600"},
        {"counterparty_id": parth, "share_amount": "600"},
    ]
    expense = create(client, headers, participants=split).json()

    response = client.put(
        f"/expenses/{expense['id']}",
        json={
            **DINNER,
            "payments": [{"counterparty_id": parth, "amount": "1200"}],
            "participants": [
                {"counterparty_id": parth, "share_amount": "200"},
                {"counterparty_id": None, "share_amount": "1000"},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert who_paid(body) == [{"counterparty_id": parth, "amount": "1200.00"}]
    assert body["participants"] == [
        {"counterparty_id": parth, "share_amount": "200.00"},
        {"counterparty_id": None, "share_amount": "1000.00"},
    ]


def test_edit_without_payments_or_shares_resets_to_all_yours(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)
    expense = create(client, headers, payments=[{"counterparty_id": parth, "amount": "1200"}]).json()

    body = client.put(f"/expenses/{expense['id']}", json=DINNER, headers=headers).json()

    assert who_paid(body) == [{"counterparty_id": None, "amount": "1200.00"}]


def test_edit_with_bad_contact_changes_nothing(client, make_user):
    headers = make_user()
    expense = create(client, headers).json()

    response = client.put(
        f"/expenses/{expense['id']}",
        json={**DINNER, "amount": "50", "counterparty_id": 999999},
        headers=headers,
    )

    assert response.status_code == 404
    assert client.get(f"/expenses/{expense['id']}", headers=headers).json()["amount"] == "1200.00"


# ---------- deleting contacts that are in use ----------


@pytest.mark.parametrize("where", ["counterparty_id", "payments", "participants"])
def test_contact_used_in_an_expense_cannot_be_deleted(client, make_user, where):
    headers = make_user()
    parth = add_contact(client, headers)

    fields = {
        "counterparty_id": {"counterparty_id": parth},
        "payments": {"payments": [{"counterparty_id": parth, "amount": "1200"}]},
        "participants": {"participants": [{"counterparty_id": parth, "share_amount": "1200"}]},
    }[where]
    create(client, headers, **fields)

    response = client.delete(f"/counterparties/{parth}", headers=headers)

    assert response.status_code == 409
    assert "Parth" in response.json()["detail"]
    assert client.get(f"/counterparties/{parth}", headers=headers).status_code == 200


def test_contact_can_be_deleted_once_its_expense_is_gone(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)
    expense = create(client, headers, payments=[{"counterparty_id": parth, "amount": "1200"}]).json()

    client.delete(f"/expenses/{expense['id']}", headers=headers)

    assert client.delete(f"/counterparties/{parth}", headers=headers).status_code == 204
