"""Tests for line items, discounts, the original amount, and payment methods."""

import pytest


BILL = {"date": "2026-09-01", "amount": "1000", "description": "Groceries"}


def create(client, headers, **fields):
    return client.post("/expenses", json={**BILL, **fields}, headers=headers)


def item(name, amount, **fields):
    return {"name": name, "amount": amount, **fields}


def add_contact(client, headers, name="Parth"):
    return client.post("/counterparties", json={"name": name}, headers=headers).json()["id"]


# ---------- discount and original amount ----------


def test_no_discount_means_original_equals_amount(client, make_user):
    body = create(client, make_user()).json()

    assert body["discount_amount"] == "0.00"
    assert body["original_amount"] == "1000.00"


def test_discount_gives_the_original_amount(client, make_user):
    body = create(client, make_user(), amount="1500", discount_amount="160").json()

    assert body["amount"] == "1500.00"
    assert body["discount_amount"] == "160.00"
    assert body["original_amount"] == "1660.00"


def test_shares_and_payments_add_up_to_the_charged_amount_not_the_original(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    response = create(
        client,
        headers,
        amount="900",
        discount_amount="100",
        participants=[
            {"counterparty_id": None, "share_amount": "450"},
            {"counterparty_id": parth, "share_amount": "450"},
        ],
    )

    assert response.status_code == 201
    assert client.get("/balances", headers=headers).json()[0]["amount"] == "450.00"


# ---------- items ----------


def test_items_are_saved_in_order(client, make_user):
    response = create(
        client,
        make_user(),
        items=[
            item("  Basmati   rice ", "600", quantity="2", unit=" KG "),
            item("Milk", "400"),
        ],
    )

    assert response.status_code == 201
    assert response.json()["items"] == [
        {"name": "Basmati rice", "quantity": "2.000", "unit": "kg", "amount": "600.00", "unit_price": None, "owners": []},
        {"name": "Milk", "quantity": "1.000", "unit": None, "amount": "400.00", "unit_price": None, "owners": []},
    ]


def test_item_owners_are_saved_and_must_add_up_to_the_price(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    response = create(
        client,
        headers,
        items=[
            {**item("Pizza", "600"), "owners": [
                {"counterparty_id": None, "amount": "300"},
                {"counterparty_id": parth, "amount": "300"},
            ]},
            item("Milk", "400"),
        ],
        # Whoever an item is for has a share of the cost.
        participants=[{"counterparty_id": None, "share_amount": "700"},
                      {"counterparty_id": parth, "share_amount": "300"}],
    )
    assert response.status_code == 201
    assert response.json()["items"][0]["owners"] == [
        {"counterparty_id": None, "amount": "300.00"},
        {"counterparty_id": parth, "amount": "300.00"},
    ]
    # Not said: nothing recorded, never guessed.
    assert response.json()["items"][1]["owners"] == []

    bad = create(
        client,
        headers,
        items=[{**item("Pizza", "600"), "owners": [{"counterparty_id": None, "amount": "500"}]},
               item("Milk", "400")],
    )
    assert bad.status_code == 422


def test_items_less_discount_must_equal_the_amount(client, make_user):
    headers = make_user()

    ok = create(
        client,
        headers,
        amount="950",
        discount_amount="50",
        items=[item("Rice", "600"), item("Milk", "400")],
    )
    wrong = create(client, headers, amount="950", items=[item("Rice", "600"), item("Milk", "400")])

    assert ok.status_code == 201
    assert ok.json()["original_amount"] == "1000.00"
    assert wrong.status_code == 422
    assert "Items add up to 1000" in wrong.json()["detail"][0]["msg"]


@pytest.mark.parametrize(
    "bad_item",
    [
        item("", "100"),
        item("   ", "100"),
        item("Rice", "0"),
        item("Rice", "-1"),
        item("Rice", "1.001"),
        item("Rice", "100", quantity="0"),
        item("Rice", "100", quantity="1.0005"),
    ],
)
def test_rejects_bad_items(client, make_user, bad_item):
    assert create(client, make_user(), amount="100", items=[bad_item]).status_code == 422


def test_rejects_negative_discount(client, make_user):
    assert create(client, make_user(), discount_amount="-5").status_code == 422


def test_edit_replaces_items_and_discount(client, make_user):
    headers = make_user()
    expense = create(
        client, headers, amount="950", discount_amount="50", items=[item("Rice", "1000")]
    ).json()

    body = client.put(f"/expenses/{expense['id']}", json=BILL, headers=headers).json()

    assert body["items"] == []
    assert body["discount_amount"] == "0.00"
    assert body["original_amount"] == "1000.00"


# ---------- charges (tax, fees, tips) ----------


def charge(kind, amount, label=None):
    return {"kind": kind, "amount": amount, **({"label": label} if label else {})}


def test_charges_are_saved_apart_from_items(client, make_user):
    headers = make_user()

    response = create(
        client,
        headers,
        amount="1080",
        discount_amount="50",
        items=[item("Rice", "600"), item("Milk", "400")],
        charges=[charge("tax", "54", "  CGST   9% "), charge("delivery", "76")],
    )

    assert response.status_code == 201
    body = response.json()
    assert [i["name"] for i in body["items"]] == ["Rice", "Milk"]
    assert body["charges"] == [
        {"kind": "tax", "label": "CGST 9%", "amount": "54.00"},
        {"kind": "delivery", "label": "Delivery", "amount": "76.00"},
    ]
    # Before the discount: items + charges.
    assert body["original_amount"] == "1130.00"
    assert client.get("/expenses", headers=headers).json()[0]["charges"] == body["charges"]


@pytest.mark.parametrize(
    ("amount", "discount", "charges", "ok"),
    [
        ("1100", "0", [charge("tax", "100")], True),       # 1000 + 100
        ("1050", "50", [charge("tax", "100")], True),      # 1000 - 50 + 100
        ("1000", "0", [charge("tax", "100")], False),      # tax left out of the amount
        ("1100", "0", [charge("fee", "50")], False),       # doesn't add up
    ],
)
def test_items_less_discount_plus_charges_must_equal_the_amount(
    client, make_user, amount, discount, charges, ok
):
    response = create(
        client,
        make_user(),
        amount=amount,
        discount_amount=discount,
        items=[item("Rice", "600"), item("Milk", "400")],
        charges=charges,
    )

    assert (response.status_code == 201) is ok


def test_charges_without_items_must_leave_something_bought(client, make_user):
    headers = make_user()

    assert create(client, headers, amount="1180", charges=[charge("tax", "180")]).status_code == 201
    assert create(client, headers, amount="100", charges=[charge("fee", "100")]).status_code == 422


@pytest.mark.parametrize(
    "bad_charge",
    [charge("gst", "10"), charge("tax", "0"), charge("tax", "-1"), charge("tax", "1.001")],
)
def test_rejects_bad_charges(client, make_user, bad_charge):
    assert create(client, make_user(), charges=[bad_charge]).status_code == 422


def test_edit_replaces_charges_and_delete_removes_them(client, make_user):
    headers = make_user()
    expense = create(
        client, headers, amount="1100", items=[item("Rice", "1000")], charges=[charge("tax", "100")]
    ).json()

    edited = client.put(
        f"/expenses/{expense['id']}",
        json={**BILL, "amount": "1020", "items": [item("Rice", "1000")], "charges": [charge("tip", "20")]},
        headers=headers,
    ).json()

    assert edited["charges"] == [{"kind": "tip", "label": "Tip", "amount": "20.00"}]
    assert client.delete(f"/expenses/{expense['id']}", headers=headers).status_code == 204


# ---------- payment methods ----------


def test_payment_method_and_provider_are_saved_and_cleaned(client, make_user):
    body = create(
        client,
        make_user(),
        payments=[{"amount": "1000", "method": " UPI ", "provider": "  Google   Pay "}],
    ).json()

    assert body["payments"] == [
        {"counterparty_id": None, "amount": "1000.00", "method": "upi", "provider": "Google Pay"}
    ]


def test_blank_method_means_not_given(client, make_user):
    body = create(client, make_user(), payments=[{"amount": "1000", "method": ""}]).json()

    assert body["payments"][0]["method"] is None


def test_rejects_unknown_payment_method(client, make_user):
    response = create(client, make_user(), payments=[{"amount": "1000", "method": "cheque"}])

    assert response.status_code == 422


def test_same_person_can_pay_in_parts(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    response = create(
        client,
        headers,
        amount="4850",
        payments=[
            {"amount": "3850", "method": "credit_card", "provider": "HDFC"},
            {"amount": "1000", "method": "cash"},
        ],
        participants=[
            {"counterparty_id": None, "share_amount": "2425"},
            {"counterparty_id": parth, "share_amount": "2425"},
        ],
    )

    assert response.status_code == 201
    assert [p["method"] for p in response.json()["payments"]] == ["credit_card", "cash"]
    # Both parts count as your payment: Parth owes you his share.
    assert client.get("/balances", headers=headers).json()[0]["amount"] == "2425.00"


def test_payments_in_parts_must_still_add_up(client, make_user):
    response = create(
        client,
        make_user(),
        payments=[{"amount": "600", "method": "card"}, {"amount": "300", "method": "cash"}],
    )

    assert response.status_code == 422


# ---------- deductions: each kind its own line ----------


def deduction(kind, amount, label=None):
    return {"kind": kind, "amount": amount, "label": label}


def test_deductions_are_kept_by_kind_and_make_up_the_discount_total(client, make_user):
    headers = make_user()

    response = create(
        client,
        headers,
        amount="929.50",
        items=[item("Shirt", "800"), item("Belt", "200")],
        deductions=[
            deduction("discount", "70", "Coupon SAVE70"),
            deduction("rounding", "0.50"),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["deductions"] == [
        {"kind": "discount", "label": "Coupon SAVE70", "amount": "70.00"},
        {"kind": "rounding", "label": "Rounding", "amount": "0.50"},
    ]
    assert body["discount_amount"] == "70.50"
    assert body["original_amount"] == "1000.00"
    assert client.get("/expenses", headers=headers).json()[0]["deductions"] == body["deductions"]


def test_a_discount_total_with_no_lines_is_one_discount(client, make_user):
    body = create(client, make_user(), amount="900", discount_amount="100").json()

    assert body["deductions"] == [{"kind": "discount", "label": "Discount", "amount": "100.00"}]
    assert body["discount_amount"] == "100.00"


def test_a_discount_total_that_disagrees_with_the_lines_is_refused(client, make_user):
    response = create(
        client,
        make_user(),
        amount="900",
        discount_amount="100",
        deductions=[deduction("rounding", "60")],
    )

    assert response.status_code == 422


def test_editing_replaces_the_deductions(client, make_user):
    headers = make_user()
    expense = create(client, headers, amount="900", deductions=[deduction("rounding", "100")]).json()

    body = client.put(
        f"/expenses/{expense['id']}",
        json={**BILL, "amount": "950", "deductions": [deduction("discount", "50")]},
        headers=headers,
    ).json()

    assert body["deductions"] == [{"kind": "discount", "label": "Discount", "amount": "50.00"}]
    assert body["discount_amount"] == "50.00"



# ---------- refunds: money given back after paying ----------


def test_a_refund_is_saved_as_its_own_event_and_shares_are_of_what_is_left(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    response = create(
        client,
        headers,
        amount="1000",
        payments=[{"amount": "1000"}],
        refunds=[{"amount": "200", "label": "  Cancelled   dish "}],
        participants=[
            {"counterparty_id": None, "share_amount": "400"},
            {"counterparty_id": parth, "share_amount": "400"},
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == "1000.00"
    assert body["deductions"] == []
    assert body["refunds"] == [
        {"counterparty_id": None, "amount": "200.00", "label": "Cancelled dish", "date": "2026-09-01"}
    ]
    # You paid 1000 and got 200 back: Parth owes you his 400.
    [balance] = client.get("/balances", headers=headers).json()
    assert balance["amount"] == "400.00"


def test_shares_must_add_up_to_what_is_left_after_refunds(client, make_user):
    response = create(
        client,
        make_user(),
        amount="1000",
        refunds=[{"amount": "200"}],
        participants=[{"counterparty_id": None, "share_amount": "1000"}],
    )

    assert response.status_code == 422


def test_without_shares_the_cost_after_refunds_is_yours(client, make_user):
    body = create(client, make_user(), amount="1000", refunds=[{"amount": "200"}]).json()

    assert body["participants"] == [{"counterparty_id": None, "share_amount": "800.00"}]


@pytest.mark.parametrize(
    "refunds",
    [
        [{"amount": "1000"}],                       # all of it or more
        [{"amount": "100", "counterparty_id": -1}], # to someone who didn't pay
    ],
)
def test_refunds_that_dont_fit_the_payments_are_refused(client, make_user, refunds):
    headers = make_user()
    parth = add_contact(client, headers)
    fixed = [{**r, "counterparty_id": parth} if r.get("counterparty_id") == -1 else r for r in refunds]

    response = create(client, headers, amount="1000", refunds=fixed)

    assert response.status_code == 422


def test_a_refund_to_the_contact_who_paid_lowers_what_you_owe_them(client, make_user):
    headers = make_user()
    parth = add_contact(client, headers)

    create(
        client,
        headers,
        amount="1000",
        payments=[{"counterparty_id": parth, "amount": "1000"}],
        refunds=[{"counterparty_id": parth, "amount": "200"}],
        participants=[
            {"counterparty_id": None, "share_amount": "400"},
            {"counterparty_id": parth, "share_amount": "400"},
        ],
    )

    # Parth paid 1000 and got 200 back: you owe him your 400.
    [balance] = client.get("/balances", headers=headers).json()
    assert balance["amount"] == "-400.00"


def test_a_unit_price_is_saved_and_must_fit_the_line(client, make_user):
    headers = make_user()
    body = {"date": "2026-09-10", "amount": "340", "description": "Juice"}

    ok = client.post("/expenses", json={**body, "items": [
        {"name": "Juice", "quantity": "4", "unit": "bottles", "amount": "340", "unit_price": "85"}]}, headers=headers)
    wrong = client.post("/expenses", json={**body, "items": [
        {"name": "Juice", "quantity": "4", "amount": "340", "unit_price": "90"}]}, headers=headers)

    assert ok.status_code == 201
    [line] = ok.json()["items"]
    assert (line["quantity"], line["unit"], line["unit_price"], line["amount"]) == ("4.000", "bottles", "85.00", "340.00")
    assert wrong.status_code == 422
