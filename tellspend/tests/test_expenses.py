import pytest

LUNCH = {"date": "2026-09-01", "amount": "350", "description": "Lunch"}

def create(client, headers, **fields):
    """Create an expense and return the response."""
    return client.post("/expenses", json={**LUNCH, **fields}, headers=headers)

# create
def test_create_returns_expense_with_exact_amount(client, make_user):
    headers = make_user()

    response = create(client, headers, amount="1234.5", description="  Lunch   at  Truffles ")

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == "1234.50"
    assert body["description"] == "Lunch at Truffles"
    assert body["date"] == "2026-09-01"

def test_create_uses_default_currency_when_none_given(client, make_user):
    headers = make_user(default_currency="USD")

    assert create(client, headers).json()["currency"] == "USD"
    assert create(client, headers, currency="eur").json()["currency"] == "EUR"

def test_create_stores_blank_description_as_none(client, make_user):
    headers = make_user()

    assert create(client, headers, description="   ").json()["description"] is None

@pytest.mark.parametrize(
    "bad_fields",
    [
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "12.345"},
        {"amount": "abc"},
        {"date": "2026-13-01"},
        {"currency": "RUPEES"},
        {"currency": "12"},
        {"description": "x" * 256},
        {"category": "food"},
        {"category": "Food & dining"},
    ],
)

def test_create_rejects_bad_input(client, make_user, bad_fields):
    headers = make_user()

    assert create(client, headers, **bad_fields).status_code == 422

def test_expenses_require_login(client):
    assert client.get("/expenses").status_code == 401
    assert client.post("/expenses", json=LUNCH).status_code == 401

# list
def test_list_shows_only_own_expenses_newest_first(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")

    older = create(client, me, date="2026-08-01").json()
    newer_first = create(client, me, date="2026-09-05").json()
    newer_second = create(client, me, date="2026-09-05").json()
    create(client, other, description="Not mine")

    listed = client.get("/expenses", headers=me).json()

    assert [e["id"] for e in listed] == [newer_second["id"], newer_first["id"], older["id"]]

# get
def test_get_returns_own_expense_and_hides_others(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    mine = create(client, me).json()
    theirs = create(client, other).json()

    assert client.get(f"/expenses/{mine['id']}", headers=me).status_code == 200
    assert client.get(f"/expenses/{theirs['id']}", headers=me).status_code == 404
    assert client.get("/expenses/999999", headers=me).status_code == 404

# replace
def test_put_replaces_every_field(client, make_user):
    headers = make_user()
    expense = create(client, headers, currency="USD").json()

    response = client.put(
        f"/expenses/{expense['id']}",
        json={"date": "2026-09-02", "amount": "99.99", "description": "Coffee"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-09-02"
    assert body["amount"] == "99.99"
    assert body["description"] == "Coffee"
    # Currency was left out, so it falls back to the default (INR), like create.
    assert body["currency"] == "INR"

def test_put_cannot_change_someone_elses_expense(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    theirs = create(client, other).json()

    response = client.put(f"/expenses/{theirs['id']}", json=LUNCH, headers=me)

    assert response.status_code == 404
    assert client.get(f"/expenses/{theirs['id']}", headers=other).json()["amount"] == "350.00"

# delete
def test_delete_removes_expense(client, make_user):
    headers = make_user()
    expense = create(client, headers).json()

    assert client.delete(f"/expenses/{expense['id']}", headers=headers).status_code == 204
    assert client.get(f"/expenses/{expense['id']}", headers=headers).status_code == 404
    
def test_delete_cannot_remove_someone_elses_expense(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    theirs = create(client, other).json()

    assert client.delete(f"/expenses/{theirs['id']}", headers=me).status_code == 404
    assert client.get(f"/expenses/{theirs['id']}", headers=other).status_code == 200



def test_create_defaults_category_to_other(client, make_user):
    headers = make_user()

    assert create(client, headers).json()["category"] == "other"
    assert create(client, headers, category="groceries").json()["category"] == "groceries"


def test_put_changes_category_and_missing_category_means_other(client, make_user):
    headers = make_user()
    expense = create(client, headers, category="travel").json()
    url = f"/expenses/{expense['id']}"

    changed = client.put(url, json={**LUNCH, "category": "food_dining"}, headers=headers)
    assert changed.json()["category"] == "food_dining"

    # Full replace: leaving category out resets it, just like currency.
    reset = client.put(url, json=LUNCH, headers=headers)
    assert reset.json()["category"] == "other"


def test_list_filters_by_category_and_only_shows_own(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")

    groceries = create(client, me, category="groceries").json()
    create(client, me, category="transport")
    create(client, other, category="groceries")

    listed = client.get("/expenses?category=groceries", headers=me).json()

    assert [e["id"] for e in listed] == [groceries["id"]]


def test_list_rejects_unknown_category_filter(client, make_user):
    headers = make_user()

    assert client.get("/expenses?category=xyz", headers=headers).status_code == 422


def test_categories_lists_every_category_with_label_in_order(client):
    response = client.get("/categories")

    assert response.status_code == 200
    categories = response.json()
    assert len(categories) == 13
    assert categories[0] == {"key": "food_dining", "label": "Food & dining"}
    assert categories[-1] == {"key": "other", "label": "Other"}



def test_an_expense_that_was_money_between_people_becomes_that(client, make_user):
    headers = make_user()
    parth = client.post("/counterparties", json={"name": "Parth"}, headers=headers).json()["id"]
    expense = client.post("/expenses", headers=headers, json={
        "date": "2026-09-29", "amount": "500", "description": "Repayment"}).json()

    moved = client.post(f"/expenses/{expense['id']}/to-settlement", headers=headers,
                        json={"counterparty_id": parth, "direction": "i_paid_them", "kind": "repayment"})

    assert moved.status_code == 201, moved.json()
    assert (moved.json()["amount"], moved.json()["kind"], moved.json()["note"]) == ("500.00", "repayment", "Repayment")
    assert client.get("/expenses", headers=headers).json() == []  # no longer spending


def test_a_saved_repayment_can_be_edited(client, make_user):
    headers = make_user()
    parth = client.post("/counterparties", json={"name": "Parth"}, headers=headers).json()["id"]
    saved = client.post("/settlements", headers=headers, json={
        "counterparty_id": parth, "direction": "they_paid_me", "amount": "500", "date": "2026-09-20"}).json()

    edited = client.put(f"/settlements/{saved['id']}", headers=headers, json={
        "counterparty_id": parth, "direction": "i_paid_them", "kind": "loan", "amount": "700", "date": "2026-09-21"})

    assert edited.status_code == 200, edited.json()
    assert (edited.json()["direction"], edited.json()["kind"], edited.json()["amount"]) == ("i_paid_them", "loan", "700.00")
    assert client.get("/balances", headers=headers).json()[0]["amount"] == "700.00"
