import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from tellspend.api.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from tellspend.api.schemas import (
    ForgotPassword,
    Message,
    ResetPassword,
    Token,
    UserResponse,
    VerifyCode,
)
from tellspend.database.config import settings
from tellspend.database.connection import get_db
from tellspend.database.models import AuthToken, User
from tellspend.services.account_emails import (
    send_password_reset_email,
    send_verification_email,
)
from tellspend.services.auth_tokens import (
    RESET_PASSWORD,
    VERIFY_EMAIL,
    check_code,
    sent_recently,
    use_token,
)
from tellspend.services.rate_limit import (
    check_email_request,
    check_login_allowed,
    client_address,
    record_login_failure,
    record_login_success,
)

# The same answer for a link that's wrong, used or expired.
BAD_LINK = "This link is invalid or has expired. Ask for a new one."


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

@router.post(
    "/token",
    response_model=Token,
)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Log in with email and password and get a token. Uses the standard
        OAuth2 form, where the email is sent as `username`. A wrong email
        and a wrong password give the same error, so nobody can find out
        which emails have accounts.

    Parameters:
        form_data: The login form (username = email, password).
        db: The database session for this request.

    Returns:
        The access token.

    Raises:
        HTTPException 401 if the email or password is wrong; 403 if the
        email isn't verified yet (only said once the password is right,
        and a code is sent); 429 after too many wrong passwords for the
        email (settings.login_max_failures*), until the window passes.
    """
    email = form_data.username.strip().lower()
    address = client_address(request)

    # Too many wrong passwords: refused before the password is checked,
    # so guessing on gives no hint. An unknown email counts the same as a
    # wrong password, so the limit doesn't show which emails have accounts.
    check_login_allowed(db, email, address)

    user = db.scalar(select(User).where(User.email == email))

    if user is None or not verify_password(form_data.password, user.password_hash):
        record_login_failure(db, email, address)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    record_login_success(db, email, address)

    # Right password, email not verified yet: send a fresh code (unless
    # one just went out) and say so; the app shows the code screen.
    if user.email_verified_at is None:
        if not sent_recently(db, user, VERIFY_EMAIL, settings.email_resend_seconds):
            send_verification_email(db, user)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email first: enter the code we sent to it.",
        )

    return Token(
        access_token=create_access_token(user.id, user.password_changed_at),
        token_type="bearer",
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Explanation:
        Return the signed-in user. The frontend calls this on startup to
        check that its saved token still works.

    Parameters:
        current_user: The signed-in user.

    Returns:
        The user's profile.
    """
    return current_user

@router.post("/verify-email", response_model=Token)
def verify_email(body: VerifyCode, db: Session = Depends(get_db)):
    """
    Explanation:
        Confirm an email address with the 6-digit code sent to it, and sign
        in. A wrong code counts as a try; after too many, or once it
        expires, a new code must be asked for. An unknown email gets the
        same answer as an expired code.

    Parameters:
        body: The email and the code.
        db: The database session for this request.

    Returns:
        A login token; 400 with what to do if the code isn't accepted.
    """
    user = db.scalar(select(User).where(User.email == body.email))

    if user is not None and user.email_verified_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already verified. Sign in instead.",
        )

    result = check_code(db, user, VERIFY_EMAIL, body.code) if user is not None else "expired"
    db.commit()

    if result == "wrong":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code isn't right. Check the email and try again.",
        )

    if result != "ok":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This code has expired or had too many tries. Ask for a new one.",
        )

    user.email_verified_at = dt.datetime.now(dt.timezone.utc)
    db.commit()

    return Token(access_token=create_access_token(user.id, user.password_changed_at), token_type="bearer")


@router.post(
    "/resend-verification",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
)
def resend_verification(body: ForgotPassword, request: Request, db: Session = Depends(get_db)):
    """
    Explanation:
        Email a new verification code (the old one stops working). No login
        is needed, since an account can't sign in until it's verified. The
        answer is the same whether or not the email has an unverified
        account; repeat requests within EMAIL_RESEND_SECONDS send nothing
        new, and one device can ask only so often an hour.

    Parameters:
        body: The email address.
        request: The HTTP request (for the client's address).
        db: The database session for this request.

    Returns:
        The same message every time (202).

    Raises:
        HTTPException 429 after too many requests from this device.
    """
    check_email_request(db, "resend", client_address(request))
    user = db.scalar(select(User).where(User.email == body.email))

    if (
        user is not None
        and user.email_verified_at is None
        and not sent_recently(db, user, VERIFY_EMAIL, settings.email_resend_seconds)
    ):
        send_verification_email(db, user)

    return Message(
        detail="If that email has an account waiting to be verified, a new code is on its way."
    )


@router.post("/forgot-password", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: ForgotPassword, request: Request, db: Session = Depends(get_db)):
    """
    Explanation:
        Email a password reset link, and say plainly what happened: no
        account with that email, a link sent, one sent moments ago, or the
        email couldn't go out. (Whether an email has an account isn't a
        secret here: signing up already says "already exists". What stops
        a script testing thousands of emails is the hourly limit per
        device.)

    Parameters:
        body: The email address.
        request: The HTTP request (for the client's address).
        db: The database session for this request.

    Returns:
        What happened (202).

    Raises:
        HTTPException 404 if no account uses the email; 429 after too many
        requests from this device; 503 if the email couldn't be sent.
    """
    check_email_request(db, "forgot", client_address(request))
    user = db.scalar(select(User).where(User.email == body.email))

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account uses this email. Check it for typos, or create an account.",
        )

    if sent_recently(db, user, RESET_PASSWORD, settings.email_resend_seconds):
        return Message(
            detail=f"We just sent a link to {user.email}. Check your inbox and spam folder, "
            "or ask again in a minute."
        )

    if not send_password_reset_email(db, user):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We couldn't send the email just now. Please try again in a few minutes.",
        )

    return Message(
        detail=f"We've sent a reset link to {user.email}. Check your inbox (and the spam folder)."
    )


@router.post("/reset-password", response_model=Message)
def reset_password(body: ResetPassword, db: Session = Depends(get_db)):
    """
    Explanation:
        Choose a new password with a reset link. Every other reset link
        stops working, every login from before is signed out, and the email
        counts as verified (the link proved the user reads it).

    Parameters:
        body: The token from the link and the new password.
        db: The database session for this request.

    Returns:
        A message; 400 if the link is wrong, used or expired.
    """
    user = use_token(db, body.token, RESET_PASSWORD)

    if user is None:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=BAD_LINK)

    now = dt.datetime.now(dt.timezone.utc)
    user.password_hash = hash_password(body.password)
    user.password_changed_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now

    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == RESET_PASSWORD,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    db.commit()

    return Message(detail="Your password is changed. Sign in with the new one.")
