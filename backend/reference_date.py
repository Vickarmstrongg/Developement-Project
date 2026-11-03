# Fix reference date for historical analytics

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
    # Latest transaction date but never later than today 

    query = scope if scope is not None else db.query(models.Transaction)
    latest = query.with_entities(func.max(models.Transaction.datetime)).scalar()
    return cap_reference_date(latest, today_provider())
