"""Keeps the app closed while a lecturer-data migration is unfinished.

The migration script records its progress in public.lecturer_migration_state.
If that table does not exist (any branch that was never migrated) this module
does nothing. If it exists, every API route except the health checks answers
503 until the status is 'complete', so partly migrated data is never shown.
"""

import time

from fastapi import HTTPException, Request
from sqlalchemy import text

STATE_TABLE = "lecturer_migration_state"
COMPLETE = "complete"
ABSENT = "absent"
CACHE_SECONDS = 5
EXEMPT_PATHS = {"/", "/db-check", "/migration-status", "/docs", "/redoc", "/openapi.json"}

_cache = {"checked_at": None, "status": None}


def read_status(engine) -> str:
    with engine.connect() as connection:
        exists = connection.execute(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"public.{STATE_TABLE}"},
        ).scalar()
        if not exists:
            return ABSENT
        row = connection.execute(
            text(f"SELECT status FROM public.{STATE_TABLE}")
        ).first()
        return row[0] if row else "unknown"


def current_status(engine, clock=time.monotonic) -> str:
    now = clock()
    checked_at = _cache["checked_at"]
    if checked_at is not None and now - checked_at < CACHE_SECONDS:
        return _cache["status"]
    status = read_status(engine)
    _cache.update(checked_at=now, status=status)
    return status


def is_ready(status: str) -> bool:
    return status in (ABSENT, COMPLETE)


def require_migration_complete(request: Request):
    if request.method == "OPTIONS" or request.url.path in EXEMPT_PATHS:
        return
    import database  # imported late so tests do not need DATABASE_URL

    try:
        status = current_status(database.engine)
    except Exception:
        raise HTTPException(status_code=503, detail="Database status could not be checked.")
    if not is_ready(status):
        raise HTTPException(
            status_code=503,
            detail="A data migration is in progress. Please try again later.",
        )
