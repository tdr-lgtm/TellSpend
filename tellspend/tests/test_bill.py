"""
Tests for working out a bill from its parts, in the assistant's builder:

    final = items + everything that adds - everything that subtracts

Every kind of adjustment goes through the same rule: taxes, service
charges, delivery, packaging, tips, fees, discounts, coupons, rounding;
as money amounts or percentages. Items can be a line price or unit price
x quantity. Payments, "the rest" and splits then use the final amount.
Each test gives the builder what the model would extract (no AI call).
"""

import datetime as dt
from decimal import Decimal

import pytest

from tellspend.api.schemas import ExpenseCreate
from tellspend.database.models import Counterparty, User
from tellspend.ingestion.builder import Builder, build_drafts, build_result
from tellspend.ingestion.extraction import SELF_REF, ExpenseExtraction, ExtractedExpenses


ME = {"ref": SELF_REF, "kind": "self"}
PARTH = {"ref": "e1", "kind": "person", "name": "Parth"}
USER = User(id=1, name="xyz", default_currency="INR")


def money(value, evidence=None):
    return {"value": value, "evidence": evidence or value}


def item(name, price=None, quantity="1", each=None):
    line = {"name": name, "quantity": quantity}
    if price:
        line["line_total"] = money(price)
    if each:
        line["unit_price"] = money(each)
    return line


def adds(kind, amount=None, percent=None, label=None):
    return adjustment(kind, "adds", amount, percent, label)


def subtracts(kind, amount=None, percent=None, label=None):
    return adjustment(kind, "subtracts", amount, percent, label)


def adjustment(kind, effect, amount, percent, label):
    entry = {"kind": kind, "effect": effect, "label": label}
    if amount:
        entry["amount"] = money(amount)
    if percent:
        entry["percent"] = money(percent, f"{percent}%")
    return entry


def build(text, decisions=(), **fields):
    extraction = ExpenseExtraction.model_validate({"excerpt": text, "entities": [ME], **fields})
    contacts = [Counterparty(id=7, name="Parth", counterparty_type="PERSON"),
                Counterparty(id=9, name="Riya", counterparty_type="PERSON"),
                Counterparty(id=10, name="Cousin", counterparty_type="PERSON", relation="cousin")]
    if decisions:
        return Builder(text=text, user=USER, contacts=contacts, today=dt.date(2026, 9, 29),
                       decisions=set(decisions)).build(extraction)
    [draft] = build_drafts([extraction], text, USER, contacts, dt.date(2026, 9, 29))
    return draft


def charges_of(draft):
    return [(c.kind, c.label, c.amount) for c in draft.charges]


def saves_cleanly(draft):
    """The draft must also pass the normal expense rules when saved."""
    ExpenseCreate(
        date=draft.date,
        amount=draft.amount,
        discount_amount=draft.discount_amount,
        items=draft.items,
        charges=draft.charges,
        deductions=draft.deductions,
        refunds=[{"amount": r.amount} for r in draft.refunds],
        payments=[{"amount": p.amount} for p in draft.payments],
        # Distinct people (null is you), as the confirm endpoint makes them.
        participants=[
            {"counterparty_id": index or None, "share_amount": s.share_amount}
            for index, s in enumerate(draft.participants)
        ],
    )
    return True


# ---------- the same rule for every kind of adjustment ----------


@pytest.mark.parametrize(
    ("text", "parts", "final"),
    [
        # Money amounts that add or subtract.
        ("shirt 1200, discount 100, tax 90", [subtracts("discount", "100"), adds("tax", "90")], "1190.00"),
        ("shirt 1200 plus delivery 49", [adds("delivery", "49")], "1249.00"),
        ("shirt 1200, tip 60", [adds("tip", "60")], "1260.00"),
        ("shirt 1200, packaging 20 and convenience fee 15",
         [adds("packaging", "20"), adds("fee", "15")], "1235.00"),
        ("shirt 1200, coupon 250 off", [subtracts("discount", "250", label="Coupon")], "950.00"),
        ("shirt 1200, rounded off 0.40 down", [subtracts("rounding", "0.40")], "1199.60"),
        # Several taxes, as Indian bills show them.
        ("shirt 1200, CGST 54 and SGST 54",
         [adds("tax", "54", label="CGST"), adds("tax", "54", label="SGST")], "1308.00"),
        # Percentages: discounts of the items, charges of what's left.
        ("shirt 1200, 18% GST", [adds("tax", percent="18", label="GST")], "1416.00"),
        ("shirt 1200, 10% off", [subtracts("discount", percent="10")], "1080.00"),
        ("shirt 1200, 10% off then 5% GST",
         [subtracts("discount", percent="10"), adds("tax", percent="5")], "1134.00"),
        # Tax is charged on the service charge too: 2.5% of 1,260.
        ("shirt 1200, service charge 5%, 2.5% CGST",
         [adds("service_charge", percent="5"), adds("tax", percent="2.5")], "1291.50"),
        # Tips aren't taxed: 10% of 1,200 only.
        ("shirt 1200, tip 100, 10% tax",
         [adds("tip", "100"), adds("tax", percent="10")], "1420.00"),
        # Delivery is taxed: 10% of 1,250.
        ("shirt 1200, delivery 50, 10% tax",
         [adds("delivery", "50"), adds("tax", percent="10")], "1375.00"),
    ],
)
def test_every_adjustment_kind_uses_the_same_rule(text, parts, final):
    draft = build(text, items=[item("shirt", "1200")], adjustments=parts)

    assert draft.problems == []
    assert draft.amount == Decimal(final)
    # Only what was bought is an item; every adjustment is a charge or
    # the discount, and together they make up the rest of the bill.
    assert [(i.name, i.amount) for i in draft.items] == [("shirt", Decimal("1200.00"))]
    added = sum((c.amount for c in draft.charges), Decimal("0"))
    assert Decimal("1200") - draft.discount_amount + added == draft.amount
    assert saves_cleanly(draft)


def test_items_discount_and_tax():
    draft = build(
        "rice 700, oil 850, discount 100, tax 130",
        items=[item("rice", "700"), item("oil", "850")],
        adjustments=[subtracts("discount", "100"), adds("tax", "130")],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("1580.00")
    assert draft.discount_amount == Decimal("100.00")
    # Tax is a charge, not something bought.
    assert [(i.name, i.amount) for i in draft.items] == [
        ("rice", Decimal("700.00")),
        ("oil", Decimal("850.00")),
    ]
    assert charges_of(draft) == [("tax", "Tax", Decimal("130.00"))]
    assert draft.notes == ["Items 1,550.00 - Discount 100.00 + Tax 130.00 = 1,580.00"]
    assert saves_cleanly(draft)


def test_order_of_adjustments_in_the_text_doesnt_matter():
    draft = build(
        "tax 90 then 10% discount on shirt 1200",
        items=[item("shirt", "1200")],
        adjustments=[adds("tax", "90"), subtracts("discount", percent="10")],
    )

    assert draft.amount == Decimal("1170.00")


def test_percentages_are_rounded_to_the_paisa():
    draft = build("book 333, 18% GST", items=[item("book", "333")], adjustments=[adds("tax", percent="18")])

    assert draft.amount == Decimal("392.94")  # 333 + 59.94


# ---------- items ----------


def test_unit_price_times_quantity():
    draft = build(
        "3 coffees at 120 each and 2 muffins at 85.50 each",
        items=[item("coffee", quantity="3", each="120"), item("muffin", quantity="2", each="85.50")],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("531.00")
    assert [i.amount for i in draft.items] == [Decimal("360.00"), Decimal("171.00")]


def test_measured_quantity_times_unit_price():
    draft = build("1.5 kg paneer at 420 per kg", items=[item("paneer", quantity="1.5", each="420")])

    assert draft.amount == Decimal("630.00")


def test_unit_price_with_tax():
    draft = build(
        "2 pizzas at 300 each + 5% GST",
        items=[item("pizza", quantity="2", each="300")],
        adjustments=[adds("tax", percent="5", label="GST")],
    )

    assert draft.amount == Decimal("630.00")


# ---------- payments and splits use the final amount ----------


def test_the_rest_of_the_payment_is_from_the_final_amount():
    draft = build(
        "my dinner 2000, 18% GST, Parth paid 1000, I paid the rest",
        entities=[ME, PARTH],
        for_refs=["me"],
        for_evidence="my dinner",
        items=[item("dinner", "2000")],
        adjustments=[adds("tax", percent="18")],
        payments=[{"payer_ref": "e1", "amount": money("1000")}, {"payer_ref": "me"}],
    )

    assert draft.problems == []
    assert [p.amount for p in draft.payments] == [Decimal("1000.00"), Decimal("1360.00")]


def test_equal_split_is_of_the_final_amount():
    draft = build(
        "dinner 1000, service charge 10%, split with Parth",
        entities=[ME, PARTH],
        items=[item("dinner", "1000")],
        adjustments=[adds("service_charge", percent="10")],
        split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}], "evidence": "split with Parth"},
    )

    assert [s.share_amount for s in draft.participants] == [Decimal("550.00"), Decimal("550.00")]


def test_cash_change_is_checked_against_the_final_amount():
    draft = build(
        "shirt 1200, tax 90, gave 1500, got 210 back",
        items=[item("shirt", "1200")],
        adjustments=[adds("tax", "90")],
        payments=[{"payer_ref": "me", "amount": money("1500"), "change": money("210")}],
    )

    assert draft.problems == []
    assert draft.payments[0].amount == Decimal("1290.00")


# ---------- a stated total ----------


def test_stated_total_that_agrees_with_the_parts():
    draft = build(
        "shirt 1200, tax 90, total 1290",
        items=[item("shirt", "1200")],
        adjustments=[adds("tax", "90")],
        total=money("1290"),
    )

    assert draft.problems == []
    assert draft.amount == Decimal("1290.00")


def test_stated_total_that_disagrees_shows_the_working():
    draft = build(
        "shirt 1200, tax 90, total 1200",
        items=[item("shirt", "1200")],
        adjustments=[adds("tax", "90")],
        total=money("1200"),
    )

    assert draft.problems == [
        "The bill works out to 1,290.00 (Items 1,200.00 + Tax 90.00 = 1,290.00), "
        "but the total you gave is 1,200.00."
    ]


def test_total_including_a_percentage_with_no_items_is_just_noted():
    draft = build(
        "paid 1,180 including 18% GST",
        total=money("1180", "1,180"),
        total_said_final="paid 1,180 including 18% GST",
        adjustments=[adds("tax", percent="18", label="GST")],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("1180.00")
    assert draft.notes == ["Includes GST (18%)."]
    assert saves_cleanly(draft)


def test_total_with_money_adjustments_and_no_items():
    draft = build(
        "paid 900 after a 100 discount",
        total=money("900"),
        total_said_final="paid 900 after",
        adjustments=[subtracts("discount", "100")],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("900.00")
    assert draft.discount_amount == Decimal("100.00")
    assert saves_cleanly(draft)


def test_one_price_and_a_coupon_asks_if_the_price_was_before_or_after_it():
    fields = {"total": money("1840", "1,840"), "adjustments": [subtracts("discount", "200")]}

    asked = build("Groceries 1,840, used a 200 coupon", **fields)
    assert asked.problems[0].startswith("Is 1,840 what you paid, or the price before")
    assert [c.decision for c in asked.choices] == ["price_final", "price_before"]

    before = build("Groceries 1,840, used a 200 coupon", decisions={"price_before"}, **fields)
    assert before.problems == [] and before.amount == Decimal("1640.00")

    final = build("Groceries 1,840, used a 200 coupon", decisions={"price_final"}, **fields)
    assert final.problems == [] and final.amount == Decimal("1840.00")


# ---------- a price given as one amount (subtotal) ----------


def test_subtotal_plus_percentage_charges():
    draft = build(
        "dinner 3,200 plus 5% service charge and 5% GST",
        description="Dinner",
        subtotal=money("3200", "3,200"),
        adjustments=[adds("service_charge", percent="5"), adds("tax", percent="5", label="GST")],
    )

    # GST is on the food plus the service charge: 5% of 3,360.
    assert draft.problems == []
    assert draft.amount == Decimal("3528.00")
    # A price with no item list isn't an item; the charges are kept.
    assert draft.items == []
    assert charges_of(draft) == [
        ("service_charge", "Service charge", Decimal("160.00")),
        ("tax", "GST", Decimal("168.00")),
    ]
    assert saves_cleanly(draft)


def test_subtotal_with_discount_tax_and_cash_change():
    draft = build(
        "groceries 2,150, discount 150, tax 96, gave 2,500 cash",
        subtotal=money("2150", "2,150"),
        adjustments=[subtracts("discount", "150"), adds("tax", "96")],
        payments=[{"payer_ref": "me", "amount": money("2500", "2,500"), "method": "cash"}],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("2096.00")
    assert draft.payments[0].amount == Decimal("2096.00")
    assert saves_cleanly(draft)


def test_subtotal_that_disagrees_with_the_items_is_a_problem():
    draft = build(
        "shirt 1200 and belt 300, 1,600 before tax",
        items=[item("shirt", "1200"), item("belt", "300")],
        subtotal=money("1600", "1,600"),
    )

    assert any("price you gave is 1,600.00" in p for p in draft.problems)


def test_adjustments_with_no_price_never_fall_back_to_the_cash_handed_over():
    draft = build(
        "discount 150, tax 96, gave 2500 cash",
        adjustments=[subtracts("discount", "150"), adds("tax", "96")],
        payments=[{"payer_ref": "me", "amount": money("2500"), "method": "cash"}],
    )

    assert draft.amount is None
    assert draft.problems


# ---------- what must stay a problem ----------


def test_the_stated_numbers_decide_what_a_tax_was_worked_out_on():
    text = "Dinner: paneer 450, naan 180, GST 5% 31.50, service charge 60, total 721.50, I paid"
    parts = dict(
        items=[item("paneer", "450"), item("naan", "180")],
        adjustments=[adds("tax", "31.50", "5", label="GST"), adds("service_charge", "60")],
        total=money("721.50"),
    )
    on_items = build(text, **parts)
    # 5% of the items and the service charge would be 34.50: that fits too.
    both = build(text.replace("31.50", "34.50").replace("721.50", "724.50"), **{
        **parts, "adjustments": [adds("tax", "34.50", "5", label="GST"), adds("service_charge", "60")],
        "total": money("724.50")})
    wrong = build(text.replace("31.50", "40"), **{
        **parts, "adjustments": [adds("tax", "40", "5", label="GST"), adds("service_charge", "60")],
        "total": money("730")})

    # 31.50 is 5% of the 630 of items: no question, taxes kept separate from items.
    assert on_items.problems == []
    assert [i.name for i in on_items.items] == ["paneer", "naan"]
    assert ("tax", "GST", Decimal("31.50")) in charges_of(on_items)
    assert on_items.amount == Decimal("721.50")
    assert both.problems == []
    # Fits no base the bill has: asked.
    assert any("5% of" in p for p in wrong.problems)


def test_percentage_of_nothing_is_a_problem():
    draft = build("18% GST on the dinner", adjustments=[adds("tax", percent="18")])

    assert any("of what" in p for p in draft.problems)


def test_adjustment_without_an_amount_is_a_problem():
    draft = build("shirt 1200 plus delivery", items=[item("shirt", "1200")], adjustments=[adds("delivery")])

    assert any("How much was the delivery" in p for p in draft.problems)
    assert draft.amount is None


def test_percentage_not_in_the_text_is_refused():
    draft = build("shirt 1200 with tax", items=[item("shirt", "1200")], adjustments=[adds("tax", percent="18")])

    assert any("couldn't find the tax" in p for p in draft.problems)
    assert draft.amount is None


def test_percentage_over_100_is_refused():
    draft = build("shirt 1200, 150% off", items=[item("shirt", "1200")],
                  adjustments=[subtracts("discount", percent="150")])

    assert draft.problems
    assert draft.amount is None


def test_discounts_bigger_than_the_bill_are_a_problem():
    draft = build("shirt 1200, discount 1500", items=[item("shirt", "1200")],
                  adjustments=[subtracts("discount", "1500")])

    assert any("whole bill or more" in p for p in draft.problems)


# ---------- charges are kept apart from items ----------


def test_charge_kinds_are_kept_and_anything_else_that_adds_is_other():
    draft = build(
        "lamp 900, delivery 50, tip 30, gift wrap 20",
        items=[item("lamp", "900")],
        adjustments=[adds("delivery", "50"), adds("tip", "30"), adds("other", "20", label="Gift wrap")],
    )

    assert draft.amount == Decimal("1000.00")
    assert [i.name for i in draft.items] == ["lamp"]
    assert charges_of(draft) == [
        ("delivery", "Delivery", Decimal("50.00")),
        ("tip", "Tip", Decimal("30.00")),
        ("other", "Gift wrap", Decimal("20.00")),
    ]
    assert saves_cleanly(draft)


def test_rounding_up_is_a_charge_and_rounding_down_a_discount():
    up = build("lamp 999.60, rounded 0.40 up", items=[item("lamp", "999.60")],
               adjustments=[adds("rounding", "0.40")])
    down = build("lamp 1000.40, rounded 0.40 down", items=[item("lamp", "1000.40")],
                 adjustments=[subtracts("rounding", "0.40")])

    assert charges_of(up) == [("rounding", "Rounding", Decimal("0.40"))]
    assert up.discount_amount == 0
    assert down.charges == [] and down.discount_amount == Decimal("0.40")
    assert up.amount == down.amount == Decimal("1000.00")
    assert saves_cleanly(up) and saves_cleanly(down)


@pytest.mark.parametrize(
    ("kind", "effect", "stated_total", "expected"),
    [
        # Items 1,000; the one unpriced adjustment is what the total leaves.
        ("tax", "adds", "1050", ("charge", "50.00")),
        ("fee", "adds", "1020", ("charge", "20.00")),
        ("discount", "subtracts", "940", ("discount", "60.00")),
    ],
)
def test_one_unpriced_adjustment_inside_the_total_is_worked_out(kind, effect, stated_total, expected):
    draft = build(
        f"lamp 600, fan 400, total {stated_total} with {kind}",
        items=[item("lamp", "600"), item("fan", "400")],
        adjustments=[adjustment(kind, effect, None, None, None)],
        total=money(stated_total),
    )

    assert draft.problems == []
    assert draft.amount == Decimal(stated_total)
    assert [i.name for i in draft.items] == ["lamp", "fan"]
    if expected[0] == "charge":
        assert [c.amount for c in draft.charges] == [Decimal(expected[1])]
    else:
        assert draft.discount_amount == Decimal(expected[1])
    assert saves_cleanly(draft)


def test_several_unpriced_charges_inside_a_total_are_asked_about_not_dropped():
    # Two unpriced charges: the total only says what they come to together.
    draft = build(
        "lamp 600, fan 400, total 1,100 with tax and delivery",
        items=[item("lamp", "600"), item("fan", "400")],
        adjustments=[adds("tax"), adds("delivery")],
        total=money("1100", "1,100"),
    )

    assert any("tax and delivery come to 100.00 together" in p for p in draft.problems)
    assert [i.name for i in draft.items] == ["lamp", "fan"]


@pytest.mark.parametrize(
    ("decisions", "amount", "difference"),
    [
        # The total is right: every part is kept, the gap is its own line.
        ({"keep_total"}, "1100.00", ("charge", "50.00")),
        # The parts are right: the total is what they come to.
        ({"keep_parts"}, "1050.00", None),
    ],
)
def test_a_total_that_disagrees_with_its_parts_is_settled_by_a_choice(decisions, amount, difference):
    text = "lamp 600, fan 400, 5% GST, total 1,100"
    extraction = ExpenseExtraction.model_validate({
        "excerpt": text,
        "entities": [ME],
        "items": [item("lamp", "600"), item("fan", "400")],
        "adjustments": [adds("tax", percent="5", label="GST")],
        "total": money("1100", "1,100"),
    })

    # Unsettled: a question, with both exact answers offered.
    [asked] = build_drafts([extraction], text, USER, [], dt.date(2026, 9, 29))
    assert asked.problems
    assert {choice.decision for choice in asked.choices} == {"keep_total", "keep_parts"}

    [draft] = build_result(
        ExtractedExpenses(expenses=[extraction]), text, USER, [], dt.date(2026, 9, 29),
        decisions=decisions,
    ).expenses

    assert draft.problems == []
    assert draft.amount == Decimal(amount)
    assert [i.name for i in draft.items] == ["lamp", "fan"]
    charges = [(c.label, c.amount) for c in draft.charges]
    assert charges[0] == ("GST", Decimal("50.00"))
    if difference:
        assert charges[1:] == [("Difference from the total", Decimal(difference[1]))]
    else:
        assert charges[1:] == []
    assert saves_cleanly(draft)
    assert saves_cleanly(draft)


def test_charges_with_no_items_are_kept_when_they_fit():
    draft = build(
        "paid 1,180 including GST 180",
        total=money("1180", "1,180"),
        adjustments=[adds("tax", "180", label="GST")],
    )

    assert draft.amount == Decimal("1180.00")
    assert draft.items == []
    assert charges_of(draft) == [("tax", "GST", Decimal("180.00"))]
    assert saves_cleanly(draft)


# ---------- who shares what, and who paid ----------

COUSIN = {"ref": "e2", "kind": "person", "relationship": "cousin"}
CAFE = {"ref": "e3", "kind": "business", "name": "Corner Cafe"}


def shares_of(draft):
    return {s.person.name: s.share_amount for s in draft.participants}


def paid_of(draft):
    return [(p.person.name, p.amount, p.method) for p in draft.payments]


def test_items_for_one_person_shared_items_and_payers_all_kept():
    draft = build(
        "wrap 540 shared by the three of us, shake 120 only Parth's, tea 60 mine; "
        "Parth paid 250 on UPI and my cousin paid the rest",
        entities=[ME, PARTH, COUSIN, CAFE],
        merchant_ref="e3",
        items=[
            {**item("wrap", "540"), "for_refs": ["me", "e1", "e2"],
             "for_evidence": "wrap 540 shared by the three of us"},
            {**item("shake", "120"), "for_refs": ["e1"], "for_evidence": "shake 120 only Parth's"},
            {**item("tea", "60"), "for_refs": ["me"], "for_evidence": "tea 60 mine"},
        ],
        payments=[
            {"payer_ref": "e1", "amount": money("250"), "method": "upi"},
            {"payer_ref": "e2"},
        ],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("720.00")
    assert paid_of(draft) == [("Parth", Decimal("250.00"), "upi"), ("Cousin", Decimal("470.00"), None)]
    # wrap 180 each; the shake is Parth's, the tea is yours; the cafe shares nothing.
    assert shares_of(draft) == {
        "You": Decimal("240.00"),
        "Parth": Decimal("300.00"),
        "Cousin": Decimal("180.00"),
    }
    # The cousin is already in People; the new cafe is only offered.
    assert draft.new_contacts == []
    assert "Add Corner Cafe to Merchants" in [c.label for c in draft.choices]
    assert saves_cleanly(draft)


def test_paying_never_makes_someone_share_an_item_nobody_was_named_for():
    draft = build(
        "wrap 540, shake 120 only Parth's; Parth paid 250 on UPI and my cousin paid the rest",
        entities=[ME, PARTH, COUSIN],
        items=[
            item("wrap", "540"),
            {**item("shake", "120"), "for_refs": ["e1"], "for_evidence": "shake 120 only Parth's"},
        ],
        payments=[
            {"payer_ref": "e1", "amount": money("250"), "method": "upi"},
            {"payer_ref": "e2"},
        ],
    )

    # Paying doesn't make the wrap the payers', and with others involved
    # it isn't assumed to be yours either: who it was for is asked.
    # Paying doesn't make the wrap theirs: whose it is is asked.
    assert draft.problems == ["Whose is the wrap? Being with Parth and your cousin doesn't say whose it is."]
    assert draft.participants == []
    assert paid_of(draft) == [("Parth", Decimal("250.00"), "upi"), ("Cousin", Decimal("410.00"), None)]


def test_an_even_split_keeps_items_that_are_someones_own():
    draft = build(
        "wrap 540 and shake 120, split equally with Parth and my cousin, the shake was Parth's",
        entities=[ME, PARTH, COUSIN],
        payments=[{"payer_ref": "me"}],
        items=[
            item("wrap", "540"),
            {**item("shake", "120"), "for_refs": ["e1"], "for_evidence": "the shake was Parth's"},
        ],
        split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}, {"ref": "e2"}], "evidence": "split equally with Parth and my cousin"},
    )

    assert draft.problems == []
    assert shares_of(draft) == {
        "You": Decimal("180.00"),
        "Parth": Decimal("300.00"),
        "Cousin": Decimal("180.00"),
    }


def test_a_partial_item_list_leaves_the_rest_shared():
    # Only the one item that's someone's own is listed; the rest is shared.
    draft = build(
        "snacks 660 split equally with Parth and my cousin, but the 120 shake was Parth's",
        entities=[ME, PARTH, COUSIN],
        payments=[{"payer_ref": "me"}],
        total=money("660"),
        items=[{**item("shake", "120"), "for_refs": ["e1"], "for_evidence": "the 120 shake was Parth's"}],
        split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}, {"ref": "e2"}], "evidence": "split equally with Parth and my cousin"},
    )

    assert draft.problems == []
    assert [(i.name, i.amount) for i in draft.items] == [
        ("shake", Decimal("120.00")),
        ("Everything else", Decimal("540.00")),
    ]
    assert shares_of(draft) == {
        "You": Decimal("180.00"),
        "Parth": Decimal("300.00"),
        "Cousin": Decimal("180.00"),
    }
    assert saves_cleanly(draft)


def test_items_over_the_total_are_still_a_problem():
    draft = build(
        "snacks 100 total, shake 120",
        total=money("100"),
        items=[item("shake", "120")],
    )

    assert draft.problems


@pytest.mark.parametrize(
    ("adjustments", "price"),
    [
        ([], "180.00"),
        ([subtracts("discount", "20")], "200.00"),
        ([adds("tax", "40", label="GST")], "140.00"),
    ],
)
def test_one_item_without_a_price_is_what_the_total_leaves(adjustments, price):
    draft = build(
        "total 760: thali 480, lassi 100, discount 20, GST 40, the rest was my paratha",
        total=money("760"),
        items=[item("thali", "480"), item("lassi", "100"), {**item("paratha"), "for_refs": ["me"], "for_evidence": "the rest was my paratha"}],
        adjustments=adjustments,
    )

    assert draft.problems == []
    assert draft.amount == Decimal("760.00")
    assert [(i.name, i.amount) for i in draft.items][-1] == ("paratha", Decimal(price))
    assert saves_cleanly(draft)


@pytest.mark.parametrize(
    ("fields"),
    [
        # Two unknown prices: the total can't say which is which.
        {"total": money("760"), "items": [item("thali", "480"), item("lassi"), item("paratha")]},
        # A percentage needs the missing price.
        {"total": money("760"), "items": [item("thali", "480"), item("paratha")],
         "adjustments": [adds("tax", percent="5")]},
        # No total at all.
        {"items": [item("thali", "480"), item("paratha")]},
    ],
)
def test_unpriced_items_that_cant_be_worked_out_are_asked_about(fields):
    draft = build("total 760: thali 480, 5% tax, lassi and paratha", **fields)

    assert any("paratha" in problem for problem in draft.problems)


# ---------- every kind of adjustment stays its own kind ----------


def test_discounts_and_rounding_are_separate_deductions():
    draft = build(
        "shirt 1200, coupon 100 off, rounded 0.40 down",
        items=[item("shirt", "1200")],
        adjustments=[
            subtracts("discount", "100", label="Coupon"),
            subtracts("rounding", "0.40"),
        ],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("1099.60")
    assert [(d.kind, d.label, d.amount) for d in draft.deductions] == [
        ("discount", "Coupon", Decimal("100.00")),
        ("rounding", "Rounding", Decimal("0.40")),
    ]
    assert draft.discount_amount == Decimal("100.40")
    assert saves_cleanly(draft)


@pytest.mark.parametrize(
    "adjustment",
    [
        adds("discount", "100"),      # a discount can't make the bill bigger
        subtracts("tax", "100"),      # a tax can't make it smaller
    ],
)
def test_an_adjustment_whose_kind_contradicts_its_effect_is_asked_about(adjustment):
    draft = build("shirt 1200, 100 adjustment", items=[item("shirt", "1200")], adjustments=[adjustment])

    assert draft.problems
    assert draft.charges == []
    assert draft.deductions == []


# ---------- refunds: money given back after paying, its own event ----------


def pay_amount(amount, payer="me"):
    return {"payer_ref": payer, "amount": money(amount)}


def refund(amount, to=None, label=None):
    entry = {"amount": money(amount), "label": label}
    if to:
        entry["to_ref"] = to
    return entry


def refunds_of(draft):
    return [(r.person.name, r.amount, r.label) for r in draft.refunds]


def test_a_refund_is_its_own_event_and_the_bill_stays_as_paid():
    draft = build(
        "2 shirts 1600, paid 1600, returned one and got 800 refunded",
        items=[item("shirts", "1600")],
        refunds=[refund("800", label="Returned one shirt")],
        payments=[pay_amount("1600")],
    )

    assert draft.problems == []
    # The bill and the payment are what happened at the till...
    assert draft.amount == Decimal("1600.00")
    assert paid_of(draft) == [("You", Decimal("1600.00"), None)]
    # ...the refund is apart, never a discount...
    assert draft.deductions == []
    assert refunds_of(draft) == [("You", Decimal("800.00"), "Returned one shirt")]
    # ...and the cost that was really borne is what's left.
    assert shares_of(draft) == {"You": Decimal("800.00")}
    assert any("refund went back to you" in note for note in draft.notes)
    assert saves_cleanly(draft)


SHARED_DINNER = dict(
    entities=[ME, PARTH],
    payments=[pay_amount("1000")],
    split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}],
           "evidence": "split equally with Parth"},
)


def build_shared_dinner(text, refunds, items=None, decisions=()):
    extraction = ExpenseExtraction.model_validate({
        "excerpt": text, "items": items or [item("dinner", "1000")], "refunds": refunds,
        **SHARED_DINNER,
    })
    [draft] = build_result(
        ExtractedExpenses(expenses=[extraction]), text, USER,
        [Counterparty(id=7, name="Parth", counterparty_type="PERSON"),
                Counterparty(id=9, name="Riya", counterparty_type="PERSON")], dt.date(2026, 9, 29),
        decisions=set(decisions),
    ).expenses
    return draft


def test_whose_share_a_refund_comes_off_is_asked_never_assumed():
    text = "dinner 1000 split equally with Parth, I paid, 200 refunded for a cancelled dish"
    draft = build_shared_dinner(text, [refund("200")])

    assert any("Whose share does" in problem for problem in draft.problems)
    assert draft.participants == []
    # Everything known is kept: the refund, who got it, the payment.
    assert refunds_of(draft) == [("You", Decimal("200.00"), None)]
    assert paid_of(draft) == [("You", Decimal("1000.00"), None)]
    assert [c.decision for c in draft.choices] == ["refund_owner:0", "refund_shared:0"]


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        # Only the share of whoever got the money back (you).
        ("refund_owner:0", {"You": Decimal("300.00"), "Parth": Decimal("500.00")}),
        # Everyone's, in proportion to their shares.
        ("refund_shared:0", {"You": Decimal("400.00"), "Parth": Decimal("400.00")}),
    ],
)
def test_the_answer_to_whose_share_is_applied_exactly(decision, expected):
    text = "dinner 1000 split equally with Parth, I paid, 200 refunded for a cancelled dish"
    draft = build_shared_dinner(text, [refund("200")], decisions=[decision])

    assert draft.problems == []
    assert shares_of(draft) == expected
    assert saves_cleanly(draft)


def test_a_refund_said_to_be_off_someones_share_is_theirs_alone():
    text = "dinner 1000 split equally with Parth, I paid, 200 back for Parth's cancelled dish"
    draft = build_shared_dinner(
        text, [{**refund("200"), "for_refs": ["e1"], "applies_evidence": "for Parth's cancelled dish"}]
    )

    assert draft.problems == []
    # You got the money back, but it lowers Parth's share, as said.
    assert refunds_of(draft) == [("You", Decimal("200.00"), None)]
    assert shares_of(draft) == {"You": Decimal("500.00"), "Parth": Decimal("300.00")}


def test_a_refund_for_an_item_comes_off_that_items_owners():
    text = "wrap 600 mine and shake 400 Parth's, I paid, the shake was returned and 400 came back"
    extraction = ExpenseExtraction.model_validate({
        "excerpt": text, "entities": [ME, PARTH],
        "items": [{**item("wrap", "600"), "for_refs": ["me"], "for_evidence": "wrap 600 mine"},
                  {**item("shake", "400"), "for_refs": ["e1"], "for_evidence": "shake 400 Parth's"}],
        "refunds": [{**refund("400"), "items": ["shake"], "applies_evidence": "the shake was returned"}],
        "payments": [{"payer_ref": "me"}],
    })
    [draft] = build_drafts([extraction], text, USER, [], dt.date(2026, 9, 29))

    assert draft.problems == []
    assert shares_of(draft) == {"You": Decimal("600.00")}


def test_with_one_person_sharing_the_refund_is_simply_theirs():
    draft = build(
        "shirts 1600, paid 1600, 800 refunded",
        items=[item("shirts", "1600")],
        refunds=[refund("800")],
        payments=[pay_amount("1600")],
    )

    assert draft.problems == []
    assert shares_of(draft) == {"You": Decimal("800.00")}


def test_a_refund_to_a_named_payer_goes_to_them():
    draft = build(
        "my shirts 1600, I paid 1000 and Parth paid 600, 500 refunded to Parth",
        entities=[ME, PARTH],
        for_refs=["me"],
        for_evidence="my shirts",
        items=[item("shirts", "1600")],
        refunds=[refund("500", to="e1")],
        payments=[pay_amount("1000"), pay_amount("600", "e1")],
    )

    assert draft.problems == []
    assert refunds_of(draft) == [("Parth", Decimal("500.00"), None)]


def test_nobody_gets_back_more_than_they_paid():
    draft = build(
        "my shirts 1600, I paid 1000 and Parth paid 600, 800 refunded to Parth",
        entities=[ME, PARTH],
        for_refs=["me"],
        for_evidence="my shirts",
        items=[item("shirts", "1600")],
        refunds=[refund("800", to="e1")],
        payments=[pay_amount("1000"), pay_amount("600", "e1")],
    )

    assert any("Parth got INR 800.00 back but paid INR 600.00" in p for p in draft.problems)


@pytest.mark.parametrize(
    ("text", "fields", "asks"),
    [
        # Several payers and nobody named: who got it is asked.
        ("shirts 1600, I paid 1000 and Parth paid 600, 800 refunded",
         {"refunds": [refund("800")],
          "payments": [pay_amount("1000"), pay_amount("600", "e1")]},
         "Who got"),
        # Money back to someone who didn't pay.
        ("shirts 1600, I paid, 800 refunded to Parth",
         {"refunds": [refund("800", to="e1")], "payments": [pay_amount("1600", "me")]},
         "didn't pay"),
        # No amount: asked, never guessed.
        ("shirts 1600, I paid, got a refund for one",
         {"refunds": [{"label": "one shirt"}], "payments": [{"payer_ref": "me"}]},
         "How much was the refund"),
        # More back than was paid.
        ("shirts 1600, I paid, 2000 refunded",
         {"refunds": [refund("2000")], "payments": [{"payer_ref": "me"}]},
         "all of the"),
    ],
)
def test_refunds_that_cant_be_placed_are_asked_about(text, fields, asks):
    draft = build(text, entities=[ME, PARTH], items=[item("shirts", "1600")], **fields)

    assert any(asks in problem for problem in draft.problems), draft.problems


# ---------- parts of one line for different people ----------

RIYA = {"ref": "e4", "kind": "person", "name": "Riya"}


def part(refs, evidence, amount=None, quantity="1"):
    entry = {"for_refs": refs, "for_evidence": evidence, "quantity": quantity}
    if amount:
        entry["amount"] = money(amount)
    return entry


def line(name, price, quantity, *parts, **fields):
    return {**item(name, price, quantity=quantity), "portions": list(parts), **fields}


def test_the_one_unpriced_part_of_a_line_is_what_the_line_leaves():
    draft = build(
        "3 coffees 360, Riya's was 100 and Parth's 140, the third was mine. I paid",
        entities=[ME, PARTH, RIYA],
        payments=[{"payer_ref": "me"}],
        items=[line(
            "coffee", "360", "3",
            part(["e4"], "Riya's was 100", "100"),
            part(["e1"], "Parth's 140", "140"),
            part(["me"], "the third was mine"),
        )],
    )

    assert draft.problems == []
    # Each coffee kept: its own price and owner, the 3 adding up to 360.
    assert [(i.name, i.quantity, i.amount, i.unit_price) for i in draft.items] == [
        ("coffee", Decimal("1"), Decimal("100.00"), Decimal("100.00")),
        ("coffee", Decimal("1"), Decimal("140.00"), Decimal("140.00")),
        ("coffee", Decimal("1"), Decimal("120.00"), Decimal("120.00")),
    ]
    assert [[(o.person.name, o.share_amount) for o in owners] for owners in draft.item_owners] == [
        [("Riya", Decimal("100.00"))], [("Parth", Decimal("140.00"))], [("You", Decimal("120.00"))]]
    assert shares_of(draft) == {"You": Decimal("120.00"), "Parth": Decimal("140.00"), "Riya": Decimal("100.00")}
    assert any("what the 360.00 leaves: 120.00" in note for note in draft.notes)


def test_unpriced_parts_of_a_line_share_its_unit_price():
    draft = build(
        "2 wraps 300, one mine and one Parth's. I paid",
        entities=[ME, PARTH],
        payments=[{"payer_ref": "me"}],
        items=[line("wrap", "300", "2", part(["me"], "one mine"), part(["e1"], "one Parth's"))],
    )

    assert draft.problems == []
    assert shares_of(draft) == {"You": Decimal("150.00"), "Parth": Decimal("150.00")}
    assert any("priced alike: 150.00 each" in note for note in draft.notes)


def test_units_no_part_claims_follow_the_rule_for_unclaimed_items():
    draft = build(
        "4 samosas 80, one was Parth's. I paid",
        entities=[ME, PARTH],
        payments=[{"payer_ref": "me"}],
        items=[line("samosa", "80", "4", part(["e1"], "one was Parth's"))],
    )

    # Priced alike, so the rest is worked out; nobody said whose the other
    # 3 were: asked, never assumed.
    assert draft.problems == ["Whose is the rest of the samosa? Being with Parth doesn't say whose it is."]
    assert draft.participants == []


def test_a_line_with_every_part_priced_needs_no_line_price():
    draft = build(
        "2 shakes, Parth's 90 and mine 110. I paid",
        entities=[ME, PARTH],
        payments=[{"payer_ref": "me"}],
        items=[line("shake", None, "2", part(["e1"], "Parth's 90", "90"), part(["me"], "mine 110", "110"))],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("200.00")
    assert shares_of(draft) == {"Parth": Decimal("90.00"), "You": Decimal("110.00")}


@pytest.mark.parametrize(
    ("text", "the_line", "asks"),
    [
        # Parts priced unlike the line's unit price: the other two aren't known.
        ("3 teas 90, Parth's was 20, the other two mine and Riya's",
         line("tea", "90", "3", part(["e1"], "Parth's was 20", "20"), part(["me"], "mine"),
              part(["e4"], "Riya's")),
         "each of the other"),
        # More parts than units.
        ("1 cake 500, half mine, half Parth's, and Riya had one",
         line("cake", "500", "1", part(["me"], "half mine"), part(["e1"], "half Parth's"),
              part(["e4"], "Riya had one")),
         "come to"),
        # Priced parts that don't make up the line.
        ("2 juices 200, Parth's 120 and mine 100",
         line("juice", "200", "2", part(["e1"], "Parth's 120", "120"), part(["me"], "mine 100", "100")),
         "come to 220.00"),
        # Whose part it is, not in the text.
        ("2 juices 200, one each",
         line("juice", "200", "2", part(["e1"], "Parth's juice"), part(["me"], "one each")),
         "who part of the juice was for"),
    ],
)
def test_parts_that_the_numbers_dont_settle_are_asked_about(text, the_line, asks):
    draft = build(text, entities=[ME, PARTH, RIYA], payments=[{"payer_ref": "me"}], items=[the_line])

    assert any(asks in problem for problem in draft.problems), draft.problems


def test_parts_given_without_counts_work_the_same():
    draft = build(
        "2 desserts 240, Parth's was 120 and the other one Riya's. I paid",
        entities=[ME, PARTH, RIYA],
        payments=[{"payer_ref": "me"}],
        items=[line(
            "dessert", "240", "2",
            part(["e1"], "Parth's was 120", "120", quantity=None),
            part(["e4"], "the other one Riya's", quantity=None),
        )],
    )

    assert draft.problems == []
    assert shares_of(draft) == {"Parth": Decimal("120.00"), "Riya": Decimal("120.00")}


def test_value_on_a_line_that_no_part_claims_is_the_rest_of_it():
    # A priced part of a mixed line: the rest of its price is unclaimed and
    # goes to the people the split names.
    draft = build(
        "snacks 650 split equally between me, Parth and Riya, except the 150 nachos, only Parth's. I paid",
        entities=[ME, PARTH, RIYA],
        payments=[{"payer_ref": "me"}],
        items=[line("snacks", "650", "1", part(["e1"], "the 150 nachos, only Parth's", "150", quantity=None))],
        split={"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}, {"ref": "e4"}],
               "evidence": "split equally between me, Parth and Riya"},
    )

    assert draft.problems == []
    assert shares_of(draft) == {
        "You": Decimal("166.67"),
        "Parth": Decimal("316.67"),
        "Riya": Decimal("166.66"),
    }
    assert [(i.name, i.amount) for i in draft.items] == [("snacks", Decimal("650.00"))]


def test_more_unpriced_parts_than_units_share_the_line_evenly():
    draft = build(
        "pizza 600 split equally between me, Parth and Riya. I paid",
        entities=[ME, PARTH, RIYA],
        payments=[{"payer_ref": "me"}],
        items=[line(
            "pizza", "600", "1",
            part(["me"], "me", quantity=None),
            part(["e1"], "Parth", quantity=None),
            part(["e4"], "Riya", quantity=None),
        )],
    )

    assert draft.problems == []
    assert shares_of(draft) == {"You": Decimal("200.00"), "Parth": Decimal("200.00"), "Riya": Decimal("200.00")}


def test_an_adjustment_listed_more_often_than_its_words_appear_counts_once():
    draft = build(
        "pasta 450 plus 5% GST",
        items=[item("pasta", "450")],
        adjustments=[adds("tax", percent="5", label="GST"), adds("tax", percent="5", label="GST")],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("472.50")
    assert any("counted once" in note for note in draft.notes)


def test_two_taxes_with_the_same_rate_are_both_kept():
    draft = build(
        "room 4000, CGST 6% and SGST 6%",
        items=[item("room", "4000")],
        adjustments=[adds("tax", percent="6", label="CGST"), adds("tax", percent="6", label="SGST")],
    )

    assert draft.amount == Decimal("4480.00")


# ---------- adjustments follow ownership, line by line ----------


def scoped(entry, items=(), owners=(), evidence=None):
    return {**entry, "items": list(items), "for_refs": list(owners), "applies_evidence": evidence}


def two_owned_items():
    return [
        {**item("pizza", "600"), "for_refs": ["me"], "for_evidence": "pizza 600 mine"},
        {**item("pasta", "400"), "for_refs": ["e1"], "for_evidence": "pasta 400 Parth's"},
    ]


def test_an_adjustment_for_particular_items_is_worked_out_on_them_and_follows_their_owners():
    draft = build(
        "pizza 600 mine, pasta 400 Parth's, 20% off the pizza, 5% GST. I paid",
        entities=[ME, PARTH],
        payments=[{"payer_ref": "me"}],
        items=two_owned_items(),
        adjustments=[
            scoped(subtracts("discount", percent="20"), items=["pizza"], evidence="20% off the pizza"),
            adds("tax", percent="5", label="GST"),
        ],
    )

    assert draft.problems == []
    # 20% of the pizza only (120); GST 5% of the 880 after it (44).
    assert draft.amount == Decimal("924.00")
    # Discount all yours; GST in proportion to what each owes before it (480 : 400).
    assert shares_of(draft) == {"You": Decimal("504.00"), "Parth": Decimal("420.00")}
    assert any(note.startswith("You: items 600.00 − Discount 120.00 + GST 24.00 = 504.00") for note in draft.notes)
    assert any(note.startswith("Parth: items 400.00 + GST 20.00 = 420.00") for note in draft.notes)
    assert saves_cleanly(draft)


def test_an_adjustment_said_to_be_someones_is_theirs():
    draft = build(
        "pizza 600 mine, pasta 400 Parth's, delivery 40 was Parth's. I paid",
        entities=[ME, PARTH],
        payments=[{"payer_ref": "me"}],
        items=two_owned_items(),
        adjustments=[scoped(adds("delivery", "40"), owners=["e1"], evidence="delivery 40 was Parth's")],
    )

    assert draft.problems == []
    assert shares_of(draft) == {"You": Decimal("600.00"), "Parth": Decimal("440.00")}


def test_each_adjustment_is_shared_on_what_it_was_worked_out_on():
    # Service charge is taxed, the tip isn't: tax follows items + service.
    draft = build(
        "pizza 600 mine, pasta 400 Parth's, 10% service charge, tip 50, 5% GST. I paid",
        entities=[ME, PARTH],
        payments=[{"payer_ref": "me"}],
        items=two_owned_items(),
        adjustments=[
            adds("service_charge", percent="10"),
            adds("tip", "50"),
            adds("tax", percent="5", label="GST"),
        ],
    )

    assert draft.problems == []
    assert draft.amount == Decimal("1205.00")
    # service 60/40, tip 30/20, GST 5% of 660/440 = 33/22
    assert shares_of(draft) == {"You": Decimal("723.00"), "Parth": Decimal("482.00")}
    assert sum(shares_of(draft).values()) == draft.amount


def test_shares_always_add_up_to_the_total_to_the_paisa():
    draft = build(
        "tea 10 mine, coffee 10 Parth's, cake 10 Riya's, 7% tax, 1 off. I paid",
        entities=[ME, PARTH, RIYA],
        payments=[{"payer_ref": "me"}],
        items=[
            {**item("tea", "10"), "for_refs": ["me"], "for_evidence": "tea 10 mine"},
            {**item("coffee", "10"), "for_refs": ["e1"], "for_evidence": "coffee 10 Parth's"},
            {**item("cake", "10"), "for_refs": ["e4"], "for_evidence": "cake 10 Riya's"},
        ],
        adjustments=[adds("tax", percent="7"), subtracts("discount", "1")],
    )

    assert draft.problems == []
    assert sum(shares_of(draft).values()) == draft.amount


@pytest.mark.parametrize(
    ("adjustment", "asks"),
    [
        # The item it's for isn't on the bill.
        (scoped(subtracts("discount", "50"), items=["burger"], evidence="50 off the burger"),
         "couldn't find it on the bill"),
        # Whose it is, not in the text.
        (scoped(adds("delivery", "40"), owners=["e1"], evidence="Parth's delivery"),
         "who or what the delivery was for"),
    ],
)
def test_adjustment_scopes_that_cant_be_backed_up_are_asked_about(adjustment, asks):
    draft = build(
        "pizza 600 mine, pasta 400 Parth's, delivery 40, 50 off the burger. I paid",
        entities=[ME, PARTH],
        payments=[{"payer_ref": "me"}],
        items=two_owned_items(),
        adjustments=[adjustment],
    )

    assert any(asks in problem for problem in draft.problems), draft.problems


def test_a_charge_on_every_item_is_on_the_whole_bill_without_more_words():
    draft = build(
        "Dinner 2000 plus 10% service charge and 5% GST on the food, tip 100",
        items=[item("Dinner", "2000")],
        adjustments=[
            {**adds("service_charge", percent="10"), "items": ["Dinner"]},
            {**adds("tax", percent="5", label="GST"), "items": ["Dinner"], "applies_evidence": "5% GST on the food"},
            adds("tip", "100"),
        ],
    )

    assert draft.problems == []
    # GST on the food alone: 100, not 5% of the food and the service charge.
    assert ("tax", "GST", Decimal("100.00")) in charges_of(draft)
    assert draft.amount == Decimal("2400.00")


def test_quantity_unit_price_and_total_are_all_kept():
    stated = build("4 bottles of juice at ₹85 each", items=[
        {"name": "juice", "quantity": "4", "unit": "bottles", "unit_price": money("85", "₹85")}])
    derived = build("3 rice bags ₹630", items=[item("rice bags", "630", quantity="3")])
    uneven = build("3 pens 100", items=[item("pen", "100", quantity="3")])

    assert [(i.quantity, i.unit, i.unit_price, i.amount) for i in stated.items] == [
        (Decimal("4"), "bottles", Decimal("85.00"), Decimal("340.00"))]
    # 630 / 3 is exactly 210: kept. 100 / 3 isn't: no unit price is made up.
    assert [(i.quantity, i.unit_price, i.amount) for i in derived.items] == [
        (Decimal("3"), Decimal("210.00"), Decimal("630.00"))]
    assert [i.unit_price for i in uneven.items] == [None]



def test_a_tax_fits_whichever_combination_of_charges_it_was_worked_out_on():
    # 10% of food 1000 + delivery 100 (not the 50 packaging) = 110.
    draft = build(
        "Food 1000, delivery 100, packaging 50, GST 10% 110",
        items=[item("Food", "1000")],
        adjustments=[adds("delivery", "100"), adds("packaging", "50"), adds("tax", "110", "10", label="GST")],
    )

    assert draft.problems == []
    assert ("tax", "GST", Decimal("110.00")) in charges_of(draft)
    assert draft.amount == Decimal("1260.00")


# ---------- a price the total and its percentages fix ----------


COURSE = "Paid 1,180 for the course including 18% GST"
# Nothing here says whether 1,180 is before or after the GST.
COURSE_UNCLEAR = "Paid 1,180 for the course, 18% GST"


def course(decisions=(), text=COURSE, **fields):
    return build(text, decisions, total=money("1180", "1,180"), items=[item("course")],
                 adjustments=[adds("tax", percent="18", label="GST")], **fields)


def test_a_total_said_to_include_a_percentage_tax_gives_the_price():
    draft = course(total_said_final="including 18% GST")

    assert draft.problems == []
    assert [(i.name, i.amount) for i in draft.items] == [("course", Decimal("1000.00"))]
    assert charges_of(draft) == [("tax", "GST", Decimal("180.00"))]
    assert draft.amount == Decimal("1180.00")
    saves_cleanly(draft)


def test_a_price_the_percentages_cant_give_exactly_is_still_asked():
    # No price plus 18% of it, rounded to the paisa, comes to 118.03.
    draft = build("Paid 118.03 for the course including 18% GST", total=money("118.03"),
                  items=[item("course")], adjustments=[adds("tax", percent="18", label="GST")],
                  total_said_final="including 18% GST")

    assert "What did the course cost?" in draft.problems


@pytest.mark.parametrize("text", [
    COURSE,
    "Paid 1,180 for the course incl. 18% GST",
    "Paid 1,180 for the course inclusive of 18% GST",
    "Paid 1,180 for the course, 18% GST included",
    "Course 1,180, GST included (18%)",
    "Paid 1,180 for the course, 18% GST inclusive",
])
def test_saying_the_tax_is_included_makes_the_total_final_even_unquoted(text):
    # The model sometimes leaves total_said_final out; the words are enough.
    draft = course(text=text)

    assert draft.problems == []
    assert draft.amount == Decimal("1180.00")
    assert [i.amount for i in draft.items] == [Decimal("1000.00")]


def test_with_nothing_saying_the_total_is_final_one_question_is_asked():
    draft = course(text=COURSE_UNCLEAR)

    assert draft.problems == ["Is 1,180 what you paid, or the price before the GST?"]
    assert [c.decision for c in draft.choices] == ["price_final", "price_before"]


@pytest.mark.parametrize(("decision", "amount", "course_price"), [
    ("price_final", Decimal("1180.00"), Decimal("1000.00")),
    ("price_before", Decimal("1392.40"), None),
])
def test_the_answer_decides_the_price(decision, amount, course_price):
    draft = course(decisions={decision}, text=COURSE_UNCLEAR)

    assert draft.problems == []
    assert draft.amount == amount
    assert [i.amount for i in draft.items] == ([course_price] if course_price else [])
