"""
Tests for keeping personal identifiers from the model: emails, UPI IDs,
card, Aadhaar, PAN, phone and account numbers are masked before the text
is sent, amounts never are, and the model's answer gets the originals
back, so evidence is still checked against what the user typed.
"""

import datetime as dt
from decimal import Decimal

import pytest

from tellspend.database.config import settings
from tellspend.database.models import User
from tellspend.ingestion import extractor
from tellspend.ingestion.builder import build_result
from tellspend.ingestion.extraction import ExpenseExtraction, ExtractedExpenses
from tellspend.ingestion.extractor import extract
from tellspend.ingestion.pii import PiiMask

MASKED = [
    ("Sent 500 to riya.sharma@gmail.com", "riya.sharma@gmail.com", "[EMAIL_1]"),
    ("Paid Parth 300 on parth99@okaxis", "parth99@okaxis", "[UPI_1]"),
    ("Paid 2,000 with card 4111 1111 1111 1111", "4111 1111 1111 1111", "[CARD_1]"),
    ("Card 4111-1111-1111-1111 charged 99", "4111-1111-1111-1111", "[CARD_1]"),
    ("Aadhaar 2345 6789 0123 for the SIM, paid 199", "2345 6789 0123", "[AADHAAR_1]"),
    ("PAN ABCPE1234F, filing fee 500", "ABCPE1234F", "[PAN_1]"),
    ("Called the plumber on 98765 43210, paid 400", "98765 43210", "[PHONE_1]"),
    ("Plumber +91 98765 43210 took 400", "+91 98765 43210", "[PHONE_1]"),
    ("Plumber 9876543210 took 400", "9876543210", "[PHONE_1]"),
    ("Office 022-24567890 courier 150", "022-24567890", "[PHONE_1]"),
    ("NEFT 5,000 to account 123456789012345", "123456789012345", "[ACCOUNT_1]"),
]


@pytest.mark.parametrize("text, original, token", MASKED)
def test_identifiers_are_masked_and_amounts_kept(text, original, token):
    masked = PiiMask().mask(text)

    assert original not in masked and token in masked
    # Every amount in the sentence is still there.
    for amount in ("500", "300", "2,000", "99", "199", "400", "150", "5,000"):
        if amount in text.replace(original, ""):
            assert amount in masked


KEPT = [
    "Lunch 350 with Parth, split equally",
    "Rent 18,000 split 60/40 between me and Parth",
    "Paid 1,20,000 for the bike",
    "Paid 12,50,000 for the car on 12/10/2026",
    "Paid by card ending 4242, total 1,999.50",
    "Bought 2 shirts at 1,499 each",
    "Flight 45,670 for 3 people",
    "Lunch @ the cafe 450",
    "Invoice 4111111111111112 is not a card: 600",  # fails the Luhn check
]


@pytest.mark.parametrize("text", KEPT)
def test_ordinary_descriptions_are_not_masked(text):
    mask = PiiMask()
    masked = mask.mask(text)

    if "Invoice" in text:
        # 16 digits that aren't a card: masked as an account number, but
        # never as a card.
        assert "[CARD" not in masked
    else:
        assert masked == text and mask.originals == {}


def test_the_same_identifier_gets_the_same_placeholder():
    mask = PiiMask()

    first = mask.mask("Paid riya@okaxis 200")
    second = mask.mask("yes, riya@okaxis is Riya")

    assert "[UPI_1]" in first and "[UPI_1]" in second and "[UPI_2]" not in second


def test_a_placeholder_the_user_typed_is_never_reused():
    mask = PiiMask()

    masked = mask.mask("[EMAIL_1] is my label; mail me at a@b.com")

    assert "[EMAIL_2]" in masked
    assert mask.restore("[EMAIL_1] and [EMAIL_2]") == "[EMAIL_1] and a@b.com"


def test_restore_reaches_every_string_in_the_answer():
    mask = PiiMask()
    mask.mask("Paid 400 to 98765 43210")
    answer = ExtractedExpenses(expenses=[ExpenseExtraction.model_validate({
        "excerpt": "Paid 400 to [PHONE_1]",
        "entities": [{"ref": "me", "kind": "self"}],
        "total": {"value": "400", "evidence": "400 to [phone_1]"},
    })])

    restored = mask.restore(answer)

    [expense] = restored.expenses
    assert expense.excerpt == "Paid 400 to 98765 43210"
    assert expense.total.evidence == "400 to 98765 43210"


class Recorder:
    def __init__(self, answer):
        self.answer, self.seen = answer, []

    def invoke(self, messages):
        self.seen.append(messages[-1][1])
        return self.answer


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(settings, "llm_attempts", 1)

    def use(answer):
        fake = Recorder(answer)
        monkeypatch.setattr(extractor, "structured_model", lambda schema=None: fake)
        return fake

    return use


TEXT = "Paid the electrician 1,200 on GPay to ramesh.k@okicici, his number is 98765 43210"


def electrician(evidence_tail: str) -> ExtractedExpenses:
    return ExtractedExpenses(expenses=[ExpenseExtraction.model_validate({
        "excerpt": f"Paid the electrician 1,200 on GPay to {evidence_tail}",
        "entities": [{"ref": "me", "kind": "self"}],
        "total": {"value": "1200", "evidence": "1,200"},
        "payments": [{"payer_ref": "me"}],
    })])


def test_the_model_never_sees_the_identifiers(model):
    fake = model(electrician("[UPI_1]"))

    extract(TEXT, dt.date(2026, 11, 6), "xyz")

    [sent] = fake.seen
    assert "ramesh.k@okicici" not in sent and "98765 43210" not in sent
    assert "[UPI_1]" in sent and "[PHONE_1]" in sent and "1,200" in sent


def test_identifiers_in_answers_are_masked_too(model):
    fake = model(electrician("[UPI_1]"))

    extract("Paid the electrician 1,200", dt.date(2026, 11, 6), "xyz",
            turns=[(["Who did you pay?"], "ramesh.k@okicici, call 98765 43210")])

    [sent] = fake.seen
    assert "ramesh.k@okicici" not in sent and "98765 43210" not in sent


def test_the_draft_is_built_from_what_the_user_typed(model):
    model(electrician("[UPI_1]"))
    user = User(id=1, name="xyz", default_currency="INR")

    extracted = extract(TEXT, dt.date(2026, 11, 6), "xyz")
    result = build_result(extracted, TEXT, user, [], dt.date(2026, 11, 6))

    [draft] = result.expenses
    assert draft.amount == Decimal("1200.00") and draft.problems == []
    assert extracted.expenses[0].excerpt.endswith("ramesh.k@okicici")
