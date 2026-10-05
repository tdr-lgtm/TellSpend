"""
Sending email.

    console   (the default) prints the email in the server's log, so in
              development the link can be clicked from there
    smtp      sends it for real, with the SMTP settings in .env
    brevo     sends it for real through Brevo's HTTPS API, for hosts that
              block the SMTP ports (Render's free plan does)

Sending never breaks the request that asked for it: a failure is logged
and reported as False, and the caller decides what to tell the user.
"""

import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import parseaddr

from tellspend.database.config import settings

logger = logging.getLogger("tellspend.mail")


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Explanation:
        Send one plain-text email with the configured backend.

    Parameters:
        to: The recipient's address.
        subject: The subject line.
        body: The plain-text body.

    Returns:
        True if it was sent (or printed), False if sending failed.
    """
    if settings.email_backend == "console":
        # WARNING so it shows with uvicorn's default log level.
        logger.warning("Email to %s\nSubject: %s\n\n%s", to, subject, body)
        return True

    if settings.email_backend == "brevo":
        return _send_with_brevo(to, subject, body)

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host or "", settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Sending email to %s failed", to)
        return False

    return True


BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _send_with_brevo(to: str, subject: str, body: str) -> bool:
    """Send one plain-text email through Brevo's API; False if it failed."""
    name, address = parseaddr(settings.email_from)
    payload = {
        "sender": {"name": name or "TellSpend", "email": address},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    request = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode(),
        headers={
            "api-key": settings.brevo_api_key or "",
            "accept": "application/json",
            "content-type": "application/json",
        },
        method="POST",
    )

    # Shorter than the browser waits for the request that sends it.
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except urllib.error.HTTPError as error:
        logger.error("Sending email to %s failed: Brevo answered %s %s",
                     to, error.code, error.read().decode(errors="replace")[:300])
        return False
    except (OSError, ValueError):
        logger.exception("Sending email to %s failed", to)
        return False

    return True
