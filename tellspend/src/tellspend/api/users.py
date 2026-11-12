import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tellspend.api.auth import get_current_user, hash_password, verify_password
from tellspend.api.schemas import AccountDelete, UserCreate, UserResponse, UserUpdate
from tellspend.database.config import settings
from tellspend.database.connection import get_db
from tellspend.database.models import Counterparty, ExpectedMoney, Expense, Settlement, User
from tellspend.services.account_emails import send_verification_email
from tellspend.services.accounts_cleanup import remove_stale_unverified
from tellspend.services.auth_tokens import VERIFY_EMAIL, sent_recently
from tellspend.services.rate_limit import check_email_request, client_address


router = APIRouter(
    prefix="/users",
    tags=["users"],
)

@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Sign up: create an account and email a 6-digit code to verify the
        address. The account can't sign in until the code is entered (a
        failed email doesn't stop the sign-up; a new code can be asked
        for). The unique email constraint in the database catches
        duplicates, even two sign-ups at the same moment.

        An email is only taken once its owner has entered the code. If
        someone signed up with another person's email and never verified
        it (they can't: the code goes to that person), signing up with it
        again replaces that unfinished account: the new name and password,
        and a fresh code to the inbox. Whoever reads the inbox finishes;
        the owner is never locked out of their own email. (An unverified
        account can't sign in, so it has nothing to lose.)

    Parameters:
        user_data: Email, name, password and default currency.
        db: The database session for this request.

    Returns:
        The new user (201).

    Raises:
        HTTPException 409 if a verified account uses the email; 429 if a
        code was sent to it moments ago (so nobody can flood an inbox), or
        after too many sign-ups from this device in an hour.
    """
    check_email_request(db, "signup", client_address(request))
    remove_stale_unverified(db)

    user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=hash_password(user_data.password),
        default_currency=user_data.default_currency,
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        user = _take_over_unverified(db, user_data)

    db.refresh(user)
    send_verification_email(db, user)
    db.refresh(user)

    return user


def _take_over_unverified(db: Session, user_data: UserCreate) -> User:
    """The unverified account with this email, now holding the new sign-up's
    details; 409 if the email is verified, 429 if a code just went out."""
    existing = db.scalar(select(User).where(User.email == user_data.email))

    if existing is None or existing.email_verified_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    if sent_recently(db, existing, VERIFY_EMAIL, settings.email_resend_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="A code was just sent to this email. Wait a minute, then try again.",
        )

    existing.name = user_data.name
    existing.password_hash = hash_password(user_data.password)
    existing.default_currency = user_data.default_currency
    # Any login made with the old password stops working.
    existing.password_changed_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return existing

@router.patch("/me", response_model=UserResponse)
def update_me(
    changes: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Change your name or default currency. Only the fields sent change.
        The default currency is used for what you record from now on;
        anything already saved keeps its own currency.

    Parameters:
        changes: The new name and/or default currency.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        You, updated.
    """
    for field, value in changes.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    body: AccountDelete,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Delete your account and everything in it (expenses, people,
        repayments), for good. Needs your password again.

    Parameters:
        body: Your password.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        Nothing (204); 403 for a wrong password.
    """
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="That password isn't right.")

    # Children first: settlements and expected money point at contacts,
    # and expenses' rows at the user and contacts.
    for model in (Settlement, ExpectedMoney, Expense):
        db.execute(delete(model).where(model.user_id == current_user.id))
    db.execute(delete(Counterparty).where(Counterparty.owner_user_id == current_user.id))
    db.delete(current_user)
    db.commit()
