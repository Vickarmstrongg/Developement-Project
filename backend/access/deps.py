"""Server-side access control (FR-08). Use these on every protected route."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

import database
import models

from .constants import Role, UserStatus
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(database.get_db),
) -> models.User:
    """Identify the caller. Role, lock and revoke status are read from the
    database on every request, so changes apply immediately."""
    unauthorised = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorised
    user_id = decode_access_token(creds.credentials)
    user = db.get(models.User, user_id) if user_id else None
    if user is None or user.status != UserStatus.ACTIVE.value or user.locked:
        raise unauthorised
    return user


def require_roles(*allowed: Role):
    """Allow only the listed roles: Depends(require_roles(Role.ADMIN, Role.MANAGER))."""
    allowed_values = {r.value for r in allowed}

    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed_values:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this")
        return user

    return checker


def require_vendor_access(vendor_id: int, user: models.User = Depends(get_current_user)) -> models.User:
    """Admin may use any vendor; Manager / Staff only vendors linked to them.
    Use on any route that has {vendor_id} in its path."""
    if user.role == Role.ADMIN.value or vendor_id in user.vendor_ids:
        return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this vendor")


# ---------- Staff must never receive revenue figures (FR-18) ----------
def strip_revenue(data):
    """Remove every key with 'revenue' in its name (plus avg_order_value) from a
    response, at any depth. Replace with exact field names once the response
    shapes are final."""
    if isinstance(data, dict):
        return {
            k: strip_revenue(v)
            for k, v in data.items()
            if "revenue" not in str(k).lower() and k != "avg_order_value"
        }
    if isinstance(data, list):
        return [strip_revenue(item) for item in data]
    return data


def shape_for_role(user: models.User, data):
    return strip_revenue(data) if user.role == Role.STAFF.value else data