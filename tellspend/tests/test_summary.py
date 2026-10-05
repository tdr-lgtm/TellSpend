"""Tests for the monthly summary."""

import datetime as dt

import pytest


def add_contact(client, headers, name="Parth"):
    return client.post("/counterparties", json={"name": name}, headers=headers).json()["id"]


def add_expense(client, headers, amount, date="2026-09-10", **fields):
    response = client.post(
        "/expenses", json={"date": date, "amount": amount, **fields}, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()


def summary(client, headers, month="2026-09"):
    response = client.get(f"/summary?month={month}", headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()


def main_currency(body):
    return body["currencies"][0]


def test_empty_month_still_shows_your_default_currency(client, make_user):
    body = summary(client, make_user(default_currency="USD"))

    assert body["month"] == "2026-09"
    assert body["currencies"] == [
        {
            "currency": "USD",
            "your_spending": "0",
            "you_paid": "0",
            "expense_count": 0,
            "by_category": [],
            "owed_to_you": "0",
            "you_owe": "0",
        }
    ]


def test_totals_and_categories_biggest_first(client, make_user):
    headers = make_user()
    add_expense(client, headers, "100", category="groceries")
    add_expense(client, headers, "300", category="food_dining")
    add_expense(client, headers, "50", category="groceries")

    body = main_currency(summary(client, headers))

    assert body["your_spending"] == "450.00"
    assert body["you_paid"] == "450.00"
    assert body["expense_count"] == 3
    assert body["by_category"] == [
        {"category": "food_dining", "amount": "300.00"},
        {"category": "groceries", "amount": "150.00"},
    ]


def test_only_the_months_expenses_count(client, make_user):
    headers = make_user()
    add_expense(client, headers, "100", date="2026-08-31")
    add_expense(client, headers, "200", date="2026-09-01")
    add_expense(client, headers, "300", date="2026-09-30")
    add_expense(client, headers, "400", date="2026-10-01")

    assert main_currency(summary(client, headers))["your_spending"] == "500.00"


def test_december_ends_at_the_new_year(client, make_user):
    headers = make_user()
    add_expense(client, headers, "100", date="2026-12-31")
    add_expense(client, headers, "200", date="2027-01-01")

    assert main_currency(summary(client, headers, "2026-12"))["your_spending"] == "100.00"


def test_spending_is_your_share_and_paid_is_what_you_paid(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)
    riya = add_contact(client, headers, "Riya")

    # You paid 900 for you and Parth: you spent 450, paid 900.
    add_expense(
        client,
        headers,
        "900",
        category="food_dining",
        participants=[
            {"counterparty_id": None, "share_amount": "450"},
            {"counterparty_id": parth, "share_amount": "450"},
        ],
    )
    # Riya paid 200 for you: you spent 200, paid nothing.
    add_expense(
        client,
        headers,
        "200",
        category="transport",
        payments=[{"counterparty_id": riya, "amount": "200"}],
    )

    body = main_currency(summary(client, headers))

    assert body["your_spending"] == "650.00"
    assert body["you_paid"] == "900.00"
    assert body["by_category"] == [
        {"category": "food_dining", "amount": "450.00"},
        {"category": "transport", "amount": "200.00"},
    ]
    assert body["owed_to_you"] == "450.00"
    assert body["you_owe"] == "200.00"


def test_expense_that_was_not_your_cost_is_not_your_spending(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    add_expense(
        client,
        headers,
        "300",
        participants=[{"counterparty_id": parth, "share_amount": "300"}],
    )

    body = main_currency(summary(client, headers))

    assert body["your_spending"] == "0"
    assert body["you_paid"] == "300.00"
    assert body["expense_count"] == 1
    assert body["by_category"] == []


def test_balances_are_all_time_not_just_this_month(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)
    add_expense(
        client,
        headers,
        "900",
        date="2026-01-15",
        participants=[
            {"counterparty_id": None, "share_amount": "450"},
            {"counterparty_id": parth, "share_amount": "450"},
        ],
    )

    body = main_currency(summary(client, headers))

    assert body["expense_count"] == 0
    assert body["owed_to_you"] == "450.00"


def test_currencies_are_kept_apart_default_first(client, make_user):
    headers = make_user(default_currency="INR")
    add_expense(client, headers, "20", currency="USD")
    add_expense(client, headers, "10", currency="EUR")
    add_expense(client, headers, "500")

    body = summary(client, headers)

    assert [(c["currency"], c["your_spending"]) for c in body["currencies"]] == [
        ("INR", "500.00"),
        ("EUR", "10.00"),
        ("USD", "20.00"),
    ]


def test_only_your_own_expenses(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    add_expense(client, other, "999")

    assert main_currency(summary(client, me))["expense_count"] == 0


def test_month_defaults_to_this_month(client, make_user):
    headers = make_user()
    today = dt.date.today()
    add_expense(client, headers, "123", date=today.isoformat())

    body = client.get("/summary", headers=headers).json()

    assert body["month"] == today.strftime("%Y-%m")
    assert main_currency(body)["your_spending"] == "123.00"


@pytest.mark.parametrize("month", ["2026-13", "2026-9", "26-09", "September", "2026-09-01"])
def test_rejects_malformed_month(client, make_user, month):
    response = client.get(f"/summary?month={month}", headers=make_user())

    assert response.status_code == 422
    assert response.json()["detail"] == "Month must look like 2026-09."


def test_summary_requires_login(client):
    assert client.get("/summary").status_code == 401
