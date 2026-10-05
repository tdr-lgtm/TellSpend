from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tellspend.api.auth import get_current_user, hash_password, verify_password
from tellspend.api.schemas import AccountDelete, UserCreate, UserResponse, UserUpdate
from tellspend.database.connection import get_db
from tellspend.database.models import Counterparty, ExpectedMoney, Expense, Settlement, User
from tellspend.services.account_emails import send_verification_email


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
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Sign up: create an account and email a 6-digit code to verify the
        address. The account can't sign in until the code is entered (a
        failed email doesn't stop the sign-up; a new code can be asked for). The unique email constraint in the database catches
        duplicates, even two sign-ups at the same moment.

    Parameters:
        user_data: Email, name, password and default currency.
        db: The database session for this request.

    Returns:
        The new user (201).

    Raises:
        HTTPException 409 if the email is already used.
    """
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

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    db.refresh(user)
    send_verification_email(db, user)
    db.refresh(user)

    return user

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
