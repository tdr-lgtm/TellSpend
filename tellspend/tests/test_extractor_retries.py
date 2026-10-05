"""
Tests for how extract_expenses copes with an unreliable model: errors,
timeouts, answers that don't parse, and empty answers are retried; a
rejected key or empty account is not; genuinely empty text stays empty.
"""

import datetime as dt

import pytest

from tellspend.database.config import settings
from tellspend.ingestion import extractor
from tellspend.ingestion.extraction import ExpenseExtraction, ExtractedExpenses
from tellspend.ingestion.extractor import (
    KEY_REJECTED,
    OUT_OF_CREDITS,
    TOO_SLOW,
    UNAVAILABLE,
    AssistantUnavailable,
    extract_expenses,
)


ONE = ExtractedExpenses(expenses=[ExpenseExtraction.model_validate({
    "excerpt": "x",
    "entities": [{"ref": "me", "kind": "self"}],
    "total": {"value": "90", "evidence": "90"},
})])
NONE = ExtractedExpenses(expenses=[])


class Status(Exception):
    """Stands in for an HTTP error from the provider's client library."""

    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FakeModel:
    """Answers with the scripted results in turn (exceptions are raised)."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(settings, "llm_attempts", 2)

    def use(*results):
        fake = FakeModel(*results)
        monkeypatch.setattr(extractor, "structured_model", lambda schema=None: fake)
        return fake

    return use


def read(text="Taxi 90"):
    return extract_expenses(text, dt.date(2026, 9, 29), "xyz")


def test_first_good_answer_is_used(model):
    fake = model(ONE)

    assert read() == ONE.expenses
    assert fake.calls == 1


@pytest.mark.parametrize("failure", [Status(500), TimeoutError("slow"), ValueError("bad json")])
def test_a_failed_attempt_is_retried(model, failure):
    fake = model(failure, ONE)

    assert read() == ONE.expenses
    assert fake.calls == 2


def test_an_unexpected_result_is_retried(model):
    fake = model("not an extraction", ONE)

    assert read() == ONE.expenses
    assert fake.calls == 2


@pytest.mark.parametrize("text", ["Snacks 45 at the station", "gave ₹500, got 20 back", "1.2k on shoes"])
def test_empty_answer_for_text_with_a_number_is_retried(model, text):
    fake = model(NONE, ONE)

    assert read(text) == ONE.expenses
    assert fake.calls == 2


def test_empty_every_time_means_nothing_found(model):
    fake = model(NONE, NONE)

    assert read("Room 204 was nice") == []
    assert fake.calls == 2


def test_empty_answer_for_text_without_numbers_is_accepted(model):
    fake = model(NONE)

    assert read("hello there") == []
    assert fake.calls == 1


@pytest.mark.parametrize(("status", "message"), [(401, KEY_REJECTED), (402, OUT_OF_CREDITS)])
def test_key_or_credit_problems_are_not_retried(model, status, message):
    fake = model(Status(status), ONE)

    with pytest.raises(AssistantUnavailable) as caught:
        read()

    assert caught.value.user_message == message
    assert fake.calls == 1


def test_every_attempt_failing_gives_a_plain_message(model):
    fake = model(Status(500), Status(502))

    with pytest.raises(AssistantUnavailable) as caught:
        read()

    assert caught.value.user_message == UNAVAILABLE
    assert fake.calls == 2


def test_timing_out_every_time_says_it_was_slow(model):
    model(TimeoutError("slow"), TimeoutError("slow"))

    with pytest.raises(AssistantUnavailable) as caught:
        read()

    assert caught.value.user_message == TOO_SLOW


def test_attempts_setting_is_respected(model, monkeypatch):
    monkeypatch.setattr(settings, "llm_attempts", 3)
    fake = model(Status(500), Status(500), ONE)

    assert read() == ONE.expenses
    assert fake.calls == 3
