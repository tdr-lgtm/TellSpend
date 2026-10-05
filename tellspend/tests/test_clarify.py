"""
Tests for answering a draft's questions: the draft's description is read
again with every answer so far, and answers are held to the same rules as
the description (every number must be in what the user typed). The model
is replaced by fixed extractions.
"""

import pytest

from tellspend.api import assistant
from tellspend.ingestion.extraction import SELF_REF, ExtractedExpenses
from tellspend.ingestion.extractor import render_clarifications


ME = {"ref": SELF_REF, "kind": "self"}


def money(value, evidence=None):
    return {"value": value, "evidence": evidence or value}


@pytest.fixture
def fake_model(monkeypatch):
    """
    Make the "model" return the given expenses, and record what it was
    asked: (text, turns) for every call.
    """
    calls = []

    def use(*expenses):
        def fake_extract(text, reference_date, user_name, turns=()):
            calls.append((text, list(turns)))
            return ExtractedExpenses.model_validate({"expenses": list(expenses)})

        monkeypatch.setattr(assistant, "extract", fake_extract)
        return calls

    return use


def clarify(client, headers, text, *turns):
    return client.post(
        "/assistant/clarify",
        json={"text": text, "turns": [{"asked": asked, "answer": answer} for asked, answer in turns]},
        headers=headers,
    )


def test_the_answers_go_to_the_model_with_the_description(client, make_user, fake_model):
    headers = make_user()
    calls = fake_model({"excerpt": "Lunch with Parth", "entities": [ME], "total": money("450")})

    response = clarify(
        client,
        headers,
        "Lunch with Parth",
        (["How much was it?"], "450"),
        (["Who paid?"], "I did"),
    )

    assert response.status_code == 200
    assert calls == [("Lunch with Parth", [(["How much was it?"], "450"), (["Who paid?"], "I did")])]


def test_a_number_from_an_answer_is_accepted(client, make_user, fake_model):
    headers = make_user()
    fake_model({"excerpt": "Lunch", "entities": [ME], "total": money("450", "it was 450")})

    [draft] = clarify(client, headers, "Lunch", (["How much was it?"], "it was 450")).json()["expenses"]

    assert draft["problems"] == []
    assert draft["amount"] == "450.00"


def test_a_number_in_neither_the_description_nor_the_answers_is_refused(client, make_user, fake_model):
    headers = make_user()
    fake_model({"excerpt": "Lunch", "entities": [ME], "total": money("500")})

    [draft] = clarify(client, headers, "Lunch", (["How much was it?"], "it was 450")).json()["expenses"]

    assert draft["problems"]
    assert draft["amount"] is None


def test_an_answer_can_settle_who_shares_it(client, make_user, fake_model):
    headers = make_user()
    client.post("/counterparties", json={"name": "Riya"}, headers=headers)
    fake_model({
        "excerpt": "Pizza 900 split equally",
        "entities": [ME, {"ref": "e1", "kind": "person", "name": "Riya"}],
        "total": money("900"),
        "payments": [{"payer_ref": "me"}],
        "split": {"method": "equal", "shares": [{"ref": "me"}, {"ref": "e1"}],
                  "evidence": "with Riya"},
    })

    [draft] = clarify(
        client, headers, "Pizza 900 split equally",
        (["It's split, but I couldn't tell who with."], "with Riya, I paid"),
    ).json()["expenses"]

    assert draft["problems"] == []
    assert {s["person"]["name"]: s["share_amount"] for s in draft["participants"]} == {
        "You": "450.00",
        "Riya": "450.00",
    }


@pytest.mark.parametrize(
    "body",
    [
        {"text": "Lunch", "turns": []},                                  # nothing answered
        {"text": "Lunch", "turns": [{"asked": ["How much?"], "answer": "  "}]},  # blank answer
        {"text": "  ", "turns": [{"asked": ["How much?"], "answer": "450"}]},    # no description
        {"text": "Lunch", "turns": [{"asked": ["How much?"], "answer": "4" * 1001}]},
    ],
)
def test_bad_requests_are_rejected(client, make_user, fake_model, body):
    fake_model()
    response = client.post("/assistant/clarify", json=body, headers=make_user())

    assert response.status_code == 422


def test_clarify_needs_login(client):
    response = client.post(
        "/assistant/clarify", json={"text": "Lunch", "turns": [{"asked": [], "answer": "450"}]}
    )

    assert response.status_code == 401


def test_clarifications_are_tagged_data_for_the_model():
    assert render_clarifications([]) == ""

    rendered = render_clarifications([(["How much?", "Who paid?"], "450, I did")])

    assert "<question>How much?</question>" in rendered
    assert "<question>Who paid?</question>" in rendered
    assert "<answer>450, I did</answer>" in rendered
