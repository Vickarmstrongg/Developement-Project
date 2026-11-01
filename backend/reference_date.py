"""Shared "as of" date for historical analytics.

The lecturer dataset contains transactions dated after the real current date.
Historical analytics must not treat those rows as history, so the reference
date is the earlier of the latest transaction date and today (South Africa).
Nothing here reads or changes any rows other than one MAX() lookup.
"""

from datetime import date, datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func

import models

APP_TIMEZONE = ZoneInfo("Africa/Johannesburg")


def today_in_app_timezone() -> date:
    return datetime.now(APP_TIMEZONE).date()


def cap_reference_date(latest: Optional[date], today: date) -> Optional[date]:
    """The earlier of the two dates; None when there are no transactions."""
    if latest is None:
        return None
    if isinstance(latest, datetime):
        latest = latest.date()
    return min(latest, today)


def get_reference_date(db, today_provider: Callable[[], date] = today_in_app_timezone,
                       scope=None) -> Optional[date]:
    """Latest transaction date, but never later than today in Africa/Johannesburg.

    Pass today_provider in tests to fix "today". `scope` may be a query on
    models.Transaction (for example restricted to a user's vendors); it
    defaults to all transactions. Returns None for an empty table.
    """
    query = scope if scope is not None else db.query(models.Transaction)
    latest = query.with_entities(func.max(models.Transaction.datetime)).scalar()
    return cap_reference_date(latest, today_provider())
