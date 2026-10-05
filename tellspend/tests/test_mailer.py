"""
Tests for sending through Brevo's API. Nothing is sent: the HTTP call is
captured instead.
"""

import io
import json
import urllib.error

import pytest

from tellspend.database.config import settings
from tellspend.services import mailer


@pytest.fixture
def brevo(monkeypatch):
    """Use the Brevo backend; every request it makes, captured."""
    monkeypatch.setattr(settings, "email_backend", "brevo")
    monkeypatch.setattr(settings, "brevo_api_key", "test-key")
    monkeypatch.setattr(settings, "email_from", "TellSpend <app@example.com>")
    requests = []

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return Answer()

    monkeypatch.setattr(mailer.urllib.request, "urlopen", urlopen)
    return requests


def test_brevo_sends_the_email_to_its_api(brevo):
    assert mailer.send_email("you@example.com", "Your code", "123456") is True

    [(request, timeout)] = brevo
    assert request.full_url == mailer.BREVO_URL
    assert request.get_header("Api-key") == "test-key"
    assert json.loads(request.data) == {
        "sender": {"name": "TellSpend", "email": "app@example.com"},
        "to": [{"email": "you@example.com"}],
        "subject": "Your code",
        "textContent": "123456",
    }
    # Gives up before the browser does.
    assert timeout < 15


def test_brevo_refusing_is_a_failed_send_not_an_error(monkeypatch, brevo):
    def refuse(request, timeout):
        raise urllib.error.HTTPError(mailer.BREVO_URL, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr(mailer.urllib.request, "urlopen", refuse)

    assert mailer.send_email("you@example.com", "Your code", "123456") is False


def test_brevo_unreachable_is_a_failed_send(monkeypatch, brevo):
    def unreachable(request, timeout):
        raise OSError("timed out")

    monkeypatch.setattr(mailer.urllib.request, "urlopen", unreachable)

    assert mailer.send_email("you@example.com", "Your code", "123456") is False
