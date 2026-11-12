"""
Checks run once when the server starts. They never stop it from starting:
they log what's wrong, in words that say how to fix it, so a broken email
setup shows up in the host's logs on deploy instead of as emails that
silently never arrive.
"""

import logging
from email.utils import parseaddr

from tellspend.database.config import settings

logger = logging.getLogger("tellspend.startup")

# Addresses from the README's examples and the default, never real senders.
_PLACEHOLDER_SENDERS = {"you@gmail.com", "no-reply@tellspend.local"}


def email_problems() -> list[str]:
    """
    Explanation:
        What's wrong with the email settings, if anything.

    Returns:
        One sentence per problem (empty when the settings look right).
    """
    backend = settings.email_backend
    if backend == "console":
        return []

    problems = []
    _, sender = parseaddr(settings.email_from)
    if not sender or sender.lower() in _PLACEHOLDER_SENDERS:
        problems.append(
            f"EMAIL_FROM is {settings.email_from!r}, an example address. Set it to the address you "
            "send from, e.g. 'TellSpend <you@yourdomain.com>' (for Brevo, a sender verified in Brevo)."
        )

    if backend == "brevo":
        key = settings.brevo_api_key or ""
        if not key:
            problems.append("EMAIL_BACKEND is brevo but BREVO_API_KEY is empty, so no email can be sent.")
        elif key.startswith("xsmtpsib-"):
            problems.append(
                "BREVO_API_KEY is a Brevo SMTP key (it starts with 'xsmtpsib-'). The brevo backend uses "
                "Brevo's API and needs an API key, which starts with 'xkeysib-': create one in Brevo under "
                "Settings > SMTP & API > API Keys. Until then every email is refused."
            )
        elif not key.startswith("xkeysib-"):
            problems.append("BREVO_API_KEY doesn't look like a Brevo API key (those start with 'xkeysib-').")

    if backend == "smtp" and not (settings.smtp_host and settings.smtp_username and settings.smtp_password):
        problems.append("EMAIL_BACKEND is smtp but SMTP_HOST, SMTP_USERNAME or SMTP_PASSWORD is missing.")

    return problems


def run_startup_checks(db_factory) -> None:
    """
    Explanation:
        Log any email setup problems, and remove sign-ups never verified
        in time. Never raises: the server starts whatever happens here.

    Parameters:
        db_factory: Makes a database session (SessionLocal).
    """
    for problem in email_problems():
        logger.error("Email setup: %s", problem)

    try:
        from tellspend.services.accounts_cleanup import remove_stale_unverified

        with db_factory() as db:
            remove_stale_unverified(db)
    except Exception:
        logger.exception("Couldn't remove old unverified sign-ups at startup")
