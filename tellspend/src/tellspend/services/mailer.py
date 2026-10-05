"""
Sending email.

    console   (the default) prints the email in the server's log, so in
              development the link can be clicked from there
    smtp      sends it for real, with the SMTP settings in .env

Sending never breaks the request that asked for it: a failure is logged
and reported as False, and the caller decides what to tell the user.
"""

import logging
import smtplib
from email.message import EmailMessage

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
