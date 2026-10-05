"""
The emails about an account: a code to verify the email, and a link to
reset the password. Each issues a fresh single-use secret (see
auth_tokens), saves it, then sends it.
"""

import datetime as dt

from sqlalchemy.orm import Session

from tellspend.database.config import settings
from tellspend.database.models import User
from tellspend.services.auth_tokens import RESET_PASSWORD, VERIFY_EMAIL, issue_code, issue_token
from tellspend.services.mailer import send_email


def _link(path: str, token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}{path}?token={token}"


def send_verification_email(db: Session, user: User) -> bool:
    """
    Explanation:
        Email the user a 6-digit code that confirms they own their address.
        Commits the new code before sending it.

    Parameters:
        db: The database session.
        user: Who to send it to.

    Returns:
        True if the email went out.
    """
    code = issue_code(db, user, VERIFY_EMAIL, dt.timedelta(minutes=settings.verify_code_minutes))
    db.commit()

    return send_email(
        user.email,
        f"{code} is your TellSpend code",
        f"Hi {user.name},\n\n"
        f"Your code to verify this email address is:\n\n    {code}\n\n"
        f"It works for {settings.verify_code_minutes} minutes. "
        "If you didn't sign up for TellSpend, you can ignore this email.",
    )


def send_password_reset_email(db: Session, user: User) -> bool:
    """
    Explanation:
        Email the user a link to choose a new password. Commits the new
        link before sending it.

    Parameters:
        db: The database session.
        user: Who to send it to.

    Returns:
        True if the email went out.
    """
    token = issue_token(
        db, user, RESET_PASSWORD, dt.timedelta(minutes=settings.reset_password_minutes)
    )
    db.commit()

    return send_email(
        user.email,
        "Reset your TellSpend password",
        f"Hi {user.name},\n\n"
        f"Someone asked to reset the password for this account. To choose a new one:\n\n"
        f"{_link('/reset-password', token)}\n\n"
        f"The link works once and for {settings.reset_password_minutes} minutes. "
        "If it wasn't you, ignore this email: your password stays the same.",
    )
