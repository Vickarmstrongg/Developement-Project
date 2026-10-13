"""Access-control settings, all read from .env (names only here, never values)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable {name}. Add it to your .env file.")
    return value


JWT_SECRET = _required("JWT_SECRET")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES") or 60)

FRONTEND_URL = (os.getenv("FRONTEND_URL") or "http://localhost:5173").rstrip("/")
CORS_ORIGINS = [
    o.strip() for o in (os.getenv("CORS_ORIGINS") or FRONTEND_URL).split(",") if o.strip()
]

INVITE_EXPIRE_HOURS = int(os.getenv("INVITE_EXPIRE_HOURS") or 24)  # BRD: 24 hours
RESET_EXPIRE_MINUTES = int(os.getenv("RESET_EXPIRE_MINUTES") or 60)
MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS") or 5)

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")