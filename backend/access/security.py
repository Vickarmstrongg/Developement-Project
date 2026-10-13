import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from . import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Treat naive datetimes as UTC so comparisons never raise."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------- passwords ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# A login for an unknown email still does one bcrypt check, so timing doesn't leak.
DUMMY_HASH = hash_password("not-a-real-password")


# ---------- invite / reset tokens ----------
def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_token(user, ttl: timedelta) -> str:
    """Store a hashed token on the user and return the raw one to email.
    Only the hash is stored (NFR-06)."""
    raw = secrets.token_urlsafe(32)
    user.token_hash = hash_token(raw)
    user.token_expires_at = utcnow() + ttl
    return raw


# ---------- access tokens (JWT) ----------
def create_access_token(user_id: int) -> str:
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None