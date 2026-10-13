from collections.abc import Mapping
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# These figures are illustrative only. Replace this fixture with queries against
# your existing, anonymised BoschCard data before using the endpoint in production.
SAMPLE_TREND = [
    {"date": "2026-10-05", "day": "Mon", "orders": 154, "customers": 133, "revenue_zar": 5900},
    {"date": "2026-10-06", "day": "Tue", "orders": 181, "customers": 156, "revenue_zar": 6750},
    {"date": "2026-10-07", "day": "Wed", "orders": 152, "customers": 131, "revenue_zar": 5710},
    {"date": "2026-10-08", "day": "Thu", "orders": 139, "customers": 120, "revenue_zar": 5260},
    {"date": "2026-10-09", "day": "Fri", "orders": 185, "customers": 160, "revenue_zar": 6890},
    {"date": "2026-10-10", "day": "Sat", "orders": 222, "customers": 192, "revenue_zar": 8340},
    {"date": "2026-10-11", "day": "Sun", "orders": 251, "customers": 224, "revenue_zar": 9470},
]

SAMPLE_HEATMAP = {
    "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "periods": ["07:00–10:00", "10:00–12:00", "12:00–14:00",
                "14:00–17:00", "17:00–20:00", "20:00–22:00"],
    # Each number is illustrative demand intensity from 0 to 100.
    "values": [
        [22, 46, 83, 52, 69, 30],
        [25, 50, 78, 58, 72, 35],
        [30, 55, 84, 60, 75, 38],
        [35, 65, 100, 72, 82, 40],
        [38, 70, 94, 77, 90, 55],
        [50, 75, 86, 85, 92, 70],
        [28, 48, 68, 58, 70, 45],
    ],
}


def get_current_user(request: Request) -> Any:
    """
    Connect this to the authentication used by your existing FastAPI app.
    This example expects your auth middleware to set request.state.user.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )
    return user


def _user_field(user: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a dictionary or a user model."""
    if isinstance(user, Mapping):
        return user.get(name, default)
    return getattr(user, name, default)


def _can_view_revenue(user: Any) -> bool:
    """Revenue is returned only to authorised roles or users with the permission."""
    role = str(_user_field(user, "role", "")).lower()
    permissions = _user_field(user, "permissions", []) or []

    if isinstance(permissions, str):
        permissions = [permissions]

    return (
        role in {"owner", "manager", "admin"}
        or "revenue:read" in set(permissions)
    )


@router.get("/overview")
def get_dashboard_overview(
    start_date: date = Query(default=date(2026, 10, 5)),
    end_date: date = Query(default=date(2026, 10, 11)),
    vendor_id: str | None = Query(default=None),
    vendor_type: str | None = Query(default=None),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Return the data the Option 2 dashboard needs:
    service outlook, KPIs, demand trend, heatmap, Rush Hour Radar and events.

    This sample endpoint accepts the dashboard filters, but its illustrative
    fixture does not filter the results. Replace the fixture with real queries
    before presenting filtered results as actual business data.
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date",
        )

    can_view_revenue = _can_view_revenue(current_user)

    trend = []
    for point in SAMPLE_TREND:
        trend.append({
            **point,
            # Do not expose revenue in the series to users without permission.
            "revenue_zar": point["revenue_zar"] if can_view_revenue else None,
        })

    return {
        "sample_data": True,
        "notice": (
            "Illustrative sample data only. Date and vendor filters are accepted "
            "but do not change these sample figures."
        ),
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "selected_filters": {
            "vendor_id": vendor_id,
            "vendor_type": vendor_type,
        },
        "currency": "ZAR",
        "permissions": {
            "can_view_revenue": can_view_revenue,
        },
        "kpis": {
            "expected_transactions": 1284,
            "expected_customers": 1116,
            "expected_revenue_zar": 48320 if can_view_revenue else None,
            "busiest_period": {
                "day": "Thursday",
                "start_time": "12:00",
                "end_time": "13:00",
            },
            "vendors_covered": 12,
        },
        "service_outlook": {
            "title": "Get ready for Thursday lunch",
            "period": "Thursday, 12:00–13:00",
            "summary": "Sample forecast shows the strongest demand around lunch.",
            "recommendations": [
                "Consider adding one front-of-house team member before 11:45.",
                "Prepare for a busier lunch service.",
            ],
        },
        "demand_trend": trend,
        "demand_heatmap": SAMPLE_HEATMAP,
        "rush_hour_radar": {
            "vendors_in_view": 12,
            "busy": 4,
            "normal": 5,
            "quiet": 3,
            "open_recommendations": 2,
        },
        "upcoming_context_events": [
            {
                "date": "2026-10-09",
                "name": "Example campus assessment period",
                "impact": "Illustrative context only",
            }
        ],
    }