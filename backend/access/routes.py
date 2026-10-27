"""Login, invite-link password setup, forgot / change password."""
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import database
import models

from . import settings
from .constants import UserStatus
from .deps import get_current_user
from .mailer import send_reset_email
from .schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    Message,
    SetPasswordRequest,
    TokenResponse,
    UserOut,
)
from .security import (
    DUMMY_HASH,
    as_utc,
    create_access_token,
    hash_password,
    hash_token,
    issue_token,
    utcnow,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(database.get_db)):
    user = db.scalar(select(models.User).where(models.User.email == body.email.lower()))

    stored = user.password_hash if user and user.password_hash else DUMMY_HASH
    password_ok = verify_password(body.password, stored)

    if not (user and user.password_hash and password_ok):
        # Count failures for real, active, unlocked accounts only (FR-03).
        if user and user.status == UserStatus.ACTIVE.value and not user.locked:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.MAX_FAILED_LOGINS:
                user.locked = True  # shows up in GET /users/locked for the Admin
            db.commit()
        raise HTTPException(401, "Incorrect email or password")

    if user.status == UserStatus.REVOKED.value:
        raise HTTPException(403, "Your access has been revoked. Please contact your administrator.")
    if user.locked:
        raise HTTPException(403, "Your account is locked. Please contact your administrator.")

    user.failed_login_attempts = 0
    db.commit()
    return TokenResponse(access_token=create_access_token(user.user_id), user=UserOut.model_validate(user))


@router.post("/set-password", response_model=Message)
def set_password(body: SetPasswordRequest, db: Session = Depends(database.get_db)):
    """Used by the invite link (UC-02) and by password-reset links."""
    user = db.scalar(select(models.User).where(models.User.token_hash == hash_token(body.token)))
    invalid = (
        user is None
        or user.token_expires_at is None
        or as_utc(user.token_expires_at) < utcnow()
        or user.status == UserStatus.REVOKED.value
    )
    if invalid:
        raise HTTPException(400, "This link is invalid or has expired. Ask your administrator for a new one.")

    user.password_hash = hash_password(body.password)
    user.status = UserStatus.ACTIVE.value  # confirms the email address too
    user.token_hash = None
    user.token_expires_at = None
    user.failed_login_attempts = 0
    user.locked = False
    db.commit()
    return Message(message="Password set. You can now log in.")

RESET_COOLDOWN = timedelta(seconds=60)

def _recently_issued(user) -> bool:
    """True if a reset link was emailed less than a minute ago (stops inbox spam)."""
    if user.token_expires_at is None:
        return False
    issued_at = as_utc(user.token_expires_at) - timedelta(minutes=settings.RESET_EXPIRE_MINUTES)
    return utcnow() - issued_at < RESET_COOLDOWN

@router.post("/forgot-password", response_model=Message)
def forgot_password(
    body: ForgotPasswordRequest,
    background: BackgroundTasks,
    db: Session = Depends(database.get_db),
):
    """The user asks for their own reset link. Same answer for every email so
    nobody can discover which addresses have accounts. Locked accounts get no
    link: the Admin decides what happens to them (UC-06)."""
    user = db.scalar(select(models.User).where(models.User.email == body.email.lower()))
    if (
        user
        and user.status == UserStatus.ACTIVE.value
        and not user.locked
        and not _recently_issued(user)
    ):
        raw = issue_token(user, timedelta(minutes=settings.RESET_EXPIRE_MINUTES))
        db.commit()
        background.add_task(send_reset_email, user.email, user.full_name or "", raw)
    return Message(message="If that email has an account, a reset link has been sent.")


@router.post("/change-password", response_model=Message)
def change_password(
    body: ChangePasswordRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return Message(message="Password changed.")


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    """Call after login or page refresh: gives role and which vendors to put in
    the location switcher (FR-07)."""
    return user