"""Admin-only user management: invites, roles, locks, revokes."""
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import database
import models
from performance import PerformanceJSONResponse

from . import settings
from .constants import Role, UserStatus
from .deps import require_roles
from .mailer import send_invite_email, send_reset_email
from .schemas import InviteRequest, Message, UserOut, UserUpdate
from .security import issue_token

router = APIRouter(
    prefix="/users",
    tags=["users (Admin only)"],
    default_response_class=PerformanceJSONResponse,
)

AdminUser = Depends(require_roles(Role.ADMIN))


def _clean_vendor_ids(db: Session, role: str, vendor_ids: list[int]) -> list[int]:
    """Staff see exactly one vendor; Managers need at least one. Every id must
    exist in vendors (user_vendor_links has no foreign key to it, so the app checks)."""
    ids = sorted(set(vendor_ids))
    if role == Role.STAFF.value and len(ids) != 1:
        raise HTTPException(400, "Staff must be linked to exactly one vendor")
    if role == Role.MANAGER.value and len(ids) < 1:
        raise HTTPException(400, "Managers must be linked to at least one vendor")
    if ids:
        found = set(
            db.scalars(select(models.Vendor.vendor_id).where(models.Vendor.vendor_id.in_(ids))).all()
        )
        missing = [i for i in ids if i not in found]
        if missing:
            raise HTTPException(400, f"Unknown vendor id(s): {missing}")
    return ids


def _get_target(db: Session, user_id: int) -> models.User:
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    if target.role == Role.ADMIN.value:
        raise HTTPException(400, "Admin accounts cannot be changed through the API")
    return target


@router.post("/invite", response_model=UserOut, status_code=201)
def invite_user(
    body: InviteRequest,
    background: BackgroundTasks,
    db: Session = Depends(database.get_db),
    admin: models.User = AdminUser,
):
    """UC-04 / FR-02: create the account as 'invited' and email the 24-hour link."""
    email = body.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(409, "A user with that email already exists")
    ids = _clean_vendor_ids(db, body.role, body.vendor_ids)

    user = models.User(
        full_name=body.full_name.strip(),
        email=email,
        role=body.role,
        status=UserStatus.INVITED.value,
        failed_login_attempts=0,
        locked=False,
    )
    user.vendor_links = [models.UserVendorLink(vendor_id=v) for v in ids]
    raw = issue_token(user, timedelta(hours=settings.INVITE_EXPIRE_HOURS))
    db.add(user)
    db.commit()
    background.add_task(send_invite_email, user.email, user.full_name, user.role, raw)
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(database.get_db), admin: models.User = AdminUser):
    return db.scalars(select(models.User).order_by(models.User.full_name)).all()


@router.get("/locked", response_model=list[UserOut])
def locked_users(db: Session = Depends(database.get_db), admin: models.User = AdminUser):
    """UC-06: poll for the failed-login pop-up. Offer revoke or reset."""
    return db.scalars(select(models.User).where(models.User.locked.is_(True))).all()


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(database.get_db),
    admin: models.User = AdminUser,
):
    """UC-05 / FR-06 / FR-07: change role, name or linked vendors."""
    user = _get_target(db, user_id)
    role = body.role or user.role
    ids = _clean_vendor_ids(db, role, body.vendor_ids if body.vendor_ids is not None else user.vendor_ids)

    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    user.role = role

    current = {link.vendor_id: link for link in user.vendor_links}
    for vendor_id, link in current.items():
        if vendor_id not in ids:
            user.vendor_links.remove(link)
    for vendor_id in ids:
        if vendor_id not in current:
            user.vendor_links.append(models.UserVendorLink(vendor_id=vendor_id))
    db.commit()
    return user


@router.delete("/{user_id}", status_code=204)
def remove_user(user_id: int, db: Session = Depends(database.get_db), admin: models.User = AdminUser):
    user = _get_target(db, user_id)
    try:
        db.delete(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        # notifications, report_exports and contextual_events point at users
        raise HTTPException(
            409,
            "This user has notifications, exports or events linked to them. Revoke their access instead.",
        )
    return Response(status_code=204)


@router.post("/{user_id}/revoke", response_model=Message)
def revoke_user(user_id: int, db: Session = Depends(database.get_db), admin: models.User = AdminUser):
    user = _get_target(db, user_id)
    user.status = UserStatus.REVOKED.value
    user.token_hash = None
    user.token_expires_at = None
    db.commit()
    return Message(message=f"Access revoked for {user.email}.")


@router.post("/{user_id}/reset-password", response_model=Message)
def reset_password(
    user_id: int,
    background: BackgroundTasks,
    db: Session = Depends(database.get_db),
    admin: models.User = AdminUser,
):
    """Admin-triggered reset for a locked user. The account unlocks once they set
    a new password from the emailed link."""
    user = _get_target(db, user_id)
    if user.status != UserStatus.ACTIVE.value:
        raise HTTPException(400, "Only active users can be sent a password reset")
    raw = issue_token(user, timedelta(minutes=settings.RESET_EXPIRE_MINUTES))
    db.commit()
    background.add_task(send_reset_email, user.email, user.full_name or "", raw)
    return Message(message=f"Password reset email sent to {user.email}.")


@router.post("/{user_id}/resend-invite", response_model=Message)
def resend_invite(
    user_id: int,
    background: BackgroundTasks,
    db: Session = Depends(database.get_db),
    admin: models.User = AdminUser,
):
    """Invites expire after 24 hours, so the Admin needs a way to send a fresh one."""
    user = _get_target(db, user_id)
    if user.status != UserStatus.INVITED.value:
        raise HTTPException(400, "This user has already accepted their invite")
    raw = issue_token(user, timedelta(hours=settings.INVITE_EXPIRE_HOURS))
    db.commit()
    background.add_task(send_invite_email, user.email, user.full_name or "", user.role, raw)
    return Message(message=f"Invite re-sent to {user.email}.")