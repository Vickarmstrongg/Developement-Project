from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

import models
from access.constants import Role
from access.deps import get_current_user
from database import get_db
from performance import PerformanceJSONResponse, timed_stage
from privacy import MIN_STUDENTS_THRESHOLD, is_suppressed
from rush_hour import get_bulk_vendor_status


router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
    default_response_class=PerformanceJSONResponse,
)

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
TIME_PERIODS = (
    {"label": "07:00-10:00", "start_hour": 7, "end_hour": 10},
    {"label": "10:00-12:00", "start_hour": 10, "end_hour": 12},
    {"label": "12:00-14:00", "start_hour": 12, "end_hour": 14},
    {"label": "14:00-17:00", "start_hour": 14, "end_hour": 17},
    {"label": "17:00-20:00", "start_hour": 17, "end_hour": 20},
    {"label": "20:00-22:00", "start_hour": 20, "end_hour": 22},
)


def _can_view_revenue(user: models.User) -> bool:
    return user.role in {Role.ADMIN.value, Role.MANAGER.value}


def _accessible_vendor_ids(user: models.User) -> list[int] | None:
    return None if user.all_vendors else user.vendor_ids


def _get_transaction_date_bounds(transaction_scope):
    bounds = transaction_scope.with_entities(
        func.max(func.date(models.Transaction.datetime)).label("latest_date"),
        func.min(func.date(models.Transaction.datetime)).label("earliest_date"),
    ).one()
    return bounds.latest_date, bounds.earliest_date


def _base_query(
    db: Session,
    start_date: date,
    end_date: date,
    vendor_id,
    vendor_type,
    accessible_vendor_ids: list[int] | None,
):
    query = (
        db.query(models.Transaction)
        .join(models.Vendor, models.Vendor.vendor_id == models.Transaction.vendor_id)
        .filter(
            func.date(models.Transaction.datetime) >= start_date,
            func.date(models.Transaction.datetime) <= end_date,
        )
    )
    if vendor_id is not None:
        query = query.filter(models.Transaction.vendor_id == vendor_id)
    if vendor_type is not None:
        query = query.filter(models.Vendor.type_id == vendor_type)
    if accessible_vendor_ids is not None:
        query = query.filter(models.Transaction.vendor_id.in_(accessible_vendor_ids))
    return query


def _get_filter_options(
    db: Session,
    accessible_vendor_ids: list[int] | None,
) -> dict[str, list[dict[str, Any]]]:
    vendor_types = (
        db.query(models.VendorType.type_id, models.VendorType.name)
        .order_by(models.VendorType.name)
    )
    vendors = (
        db.query(
            models.Vendor.vendor_id,
            models.Vendor.name,
            models.Vendor.type_id,
        )
        .order_by(models.Vendor.name, models.Vendor.vendor_id)
    )
    if accessible_vendor_ids is not None:
        vendors = vendors.filter(models.Vendor.vendor_id.in_(accessible_vendor_ids))
        vendor_types = (
            db.query(models.VendorType.type_id, models.VendorType.name)
            .join(models.Vendor, models.Vendor.type_id == models.VendorType.type_id)
            .filter(models.Vendor.vendor_id.in_(accessible_vendor_ids))
            .distinct()
            .order_by(models.VendorType.name)
        )
    return {
        "vendor_types": [
            {"id": row.type_id, "name": row.name}
            for row in vendor_types.all()
        ],
        "vendors": [
            {
                "id": row.vendor_id,
                "name": row.name,
                "vendor_type_id": row.type_id,
            }
            for row in vendors.all()
        ],
    }


@timed_stage("dashboard.heatmap")
def _build_heatmap(db: Session, base_query) -> list[dict[str, Any]]:
    hour = func.extract("hour", models.Transaction.datetime)
    period_index = case(
        *((((hour >= period["start_hour"]) & (hour < period["end_hour"])), index)
          for index, period in enumerate(TIME_PERIODS)),
        else_=None,
    )
    weekday = func.extract("isodow", models.Transaction.datetime) - 1
    rows = (
        base_query.with_entities(
            weekday.label("weekday"),
            period_index.label("period_index"),
            func.count(models.Transaction.transaction_id).label("transactions"),
            func.count(func.distinct(models.Transaction.student_id)).label("students"),
        )
        .filter(period_index.is_not(None))
        .group_by(weekday, period_index)
        .all()
    )

    by_cell = {
        (int(row.weekday), int(row.period_index)): row
        for row in rows
    }
    days = []
    for day_index, day_name in enumerate(DAY_NAMES):
        cells = []
        for period_index, period in enumerate(TIME_PERIODS):
            row = by_cell.get((day_index, period_index))
            if row is None:
                cells.append({"status": "no_data", "transactions": None})
            elif is_suppressed(row.students):
                cells.append({"status": "suppressed", "transactions": None})
            else:
                cells.append({
                    "status": "available",
                    "transactions": int(row.transactions),
                })
        days.append({"day": day_name, "cells": cells})
    return days


@router.get("/overview")
@timed_stage("dashboard.overview")
def get_dashboard_overview(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    vendor_id: int | None = Query(default=None, gt=0),
    vendor_type: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict[str, Any]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date",
        )

    accessible_vendor_ids = _accessible_vendor_ids(current_user)
    transaction_scope = db.query(models.Transaction)
    if accessible_vendor_ids is not None:
        transaction_scope = transaction_scope.filter(
            models.Transaction.vendor_id.in_(accessible_vendor_ids)
        )
    latest_date, earliest_date = _get_transaction_date_bounds(transaction_scope)
    if latest_date is None:
        return {
            "sample_data": False,
            "access_mode": "authenticated",
            "date_range": {"start": None, "end": None},
            "selected_filters": {
                "vendor_id": vendor_id,
                "vendor_type": vendor_type,
            },
            "permissions": {"can_view_revenue": _can_view_revenue(current_user)},
            "filter_options": _get_filter_options(db, accessible_vendor_ids),
            "kpis": {
                "total_transactions": None,
                "distinct_customers": None,
                "vendors_covered": 0,
                "status": "no_data",
            },
            "demand_trend": [],
            "demand_heatmap": {
                "days": list(DAY_NAMES),
                "periods": list(TIME_PERIODS),
                "values": [],
            },
            "service_outlook": {
                "status": "unavailable",
                "reason": "No transaction history is available.",
            },
            "rush_hour_radar": {
                "status": "unavailable",
                "reason": "No transaction history is available.",
            },
            "upcoming_context_events": [],
            "privacy_policy": {
                "suppression_threshold": MIN_STUDENTS_THRESHOLD,
                "review_required": False,
            },
        }

    end_date = end_date or latest_date
    start_date = start_date or max(earliest_date, end_date - timedelta(days=6))
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date",
        )

    if vendor_id is not None:
        vendor_query = (
            db.query(models.Vendor.vendor_id, models.Vendor.type_id)
            .filter(models.Vendor.vendor_id == vendor_id)
        )
        if accessible_vendor_ids is not None:
            vendor_query = vendor_query.filter(
                models.Vendor.vendor_id.in_(accessible_vendor_ids)
            )
        vendor = vendor_query.first()
        if vendor is None:
            raise HTTPException(status_code=404, detail="Vendor not found")
        if vendor_type is not None and vendor.type_id != vendor_type:
            raise HTTPException(
                status_code=422,
                detail="vendor_id does not belong to the selected vendor_type",
            )
    if vendor_type is not None:
        vendor_type_exists = (
            db.query(models.VendorType.type_id)
            .filter(models.VendorType.type_id == vendor_type)
            .first()
        )
        if vendor_type_exists is None:
            raise HTTPException(status_code=422, detail="Unknown vendor type")

    base = _base_query(
        db,
        start_date,
        end_date,
        vendor_id,
        vendor_type,
        accessible_vendor_ids,
    )
    can_view_revenue = _can_view_revenue(current_user)
    summary_fields = [
        func.count(models.Transaction.transaction_id).label("transactions"),
        func.count(func.distinct(models.Transaction.student_id)).label("students"),
        func.count(func.distinct(models.Transaction.vendor_id)).label("vendors"),
    ]
    if can_view_revenue:
        summary_fields.append(func.sum(models.Transaction.value).label("revenue"))
    summary = base.with_entities(*summary_fields).one()
    has_transactions = summary.transactions > 0
    total_suppressed = has_transactions and is_suppressed(summary.students)

    kpis: dict[str, Any] = {
        "total_transactions": (
            int(summary.transactions) if has_transactions and not total_suppressed else None
        ),
        "distinct_customers": (
            int(summary.students) if has_transactions and not total_suppressed else None
        ),
        "vendors_covered": int(summary.vendors),
        "status": (
            "no_data" if not has_transactions
            else "suppressed" if total_suppressed
            else "available"
        ),
    }
    if can_view_revenue:
        kpis["revenue"] = (
            float(summary.revenue or 0)
            if has_transactions and not total_suppressed
            else None
        )

    trend_fields = [
        func.date(models.Transaction.datetime).label("date"),
        func.count(models.Transaction.transaction_id).label("transactions"),
        func.count(func.distinct(models.Transaction.student_id)).label("students"),
    ]
    if can_view_revenue:
        trend_fields.append(func.sum(models.Transaction.value).label("revenue"))
    trend_rows = (
        base.with_entities(*trend_fields)
        .group_by(func.date(models.Transaction.datetime))
        .order_by(func.date(models.Transaction.datetime))
        .all()
    )
    trend = []
    for row in trend_rows:
        suppressed = is_suppressed(row.students)
        point: dict[str, Any] = {
            "date": row.date.isoformat(),
            "transactions": None if suppressed else int(row.transactions),
            "status": "suppressed" if suppressed else "available",
        }
        if can_view_revenue:
            point["revenue"] = None if suppressed else float(row.revenue or 0)
        trend.append(point)

    heatmap = _build_heatmap(db, base)
    available_cells = [
        (day["day"], TIME_PERIODS[index]["label"], cell["transactions"])
        for day in heatmap
        for index, cell in enumerate(day["cells"])
        if cell["status"] == "available"
    ]
    busiest_period = None
    if available_cells:
        busiest_period = {
            "day": available_cells[0][0],
            "period": available_cells[0][1],
        }
        busiest = max(available_cells, key=lambda item: item[2])
        busiest_period = {"day": busiest[0], "period": busiest[1]}

    base_vendor_ids = [
        row[0] for row in (
            base.with_entities(models.Transaction.vendor_id)
            .distinct()
            .all()
        )
    ]
    radar = {
        "status": "unavailable",
        "reason": "No vendors have transactions in the selected date range.",
    }
    if base_vendor_ids:
        reference_weekday = latest_date.weekday()
        statuses = get_bulk_vendor_status(
            db,
            base_vendor_ids,
            reference_weekday,
            12,
            latest_date,
        )
        visible_levels = [
            value["level"]
            for value in statuses.values()
            if value["status"] == "ok"
        ]
        if visible_levels:
            radar = {
                "status": "available",
                "reference_date": latest_date.isoformat(),
                "reference_period": "12:00-13:00",
                "vendors_in_view": len(visible_levels),
                "busy": visible_levels.count("busy"),
                "normal": visible_levels.count("normal"),
                "quiet": visible_levels.count("quiet"),
            }
        else:
            radar = {
                "status": "unavailable",
                "reason": "Radar statuses are suppressed by the existing privacy rule.",
                "reference_date": latest_date.isoformat(),
            }

    upcoming_until = end_date + timedelta(days=30)
    event_rows = (
        db.query(models.ContextualEvent)
        .filter(
            models.ContextualEvent.start_date <= upcoming_until,
            models.ContextualEvent.end_date >= end_date,
        )
        .order_by(models.ContextualEvent.start_date, models.ContextualEvent.event_id)
        .limit(10)
        .all()
    )
    upcoming_events = [
        {
            "event_id": event.event_id,
            "name": event.name,
            "event_type": event.event_type,
            "start_date": event.start_date.isoformat(),
            "end_date": event.end_date.isoformat(),
            "location": event.location,
        }
        for event in event_rows
    ]

    service_outlook = (
        {
            "status": "available",
            "kind": "historical",
            "title": f"Historically busiest: {busiest_period['day']} {busiest_period['period']}",
            "source": "Historical transaction aggregates for the selected filters and dates.",
            "recommendation": (
                "Review staffing and preparation ahead of this historically busy period. "
                "This is not a forecast."
            ),
        }
        if busiest_period
        else {
            "status": "unavailable",
            "kind": "historical",
            "reason": (
                "No period has enough distinct customers to show a privacy-safe "
                "historical demand insight."
            ),
        }
    )

    selected_type = None
    if vendor_type is not None:
        selected_type = (
            db.query(models.VendorType.name)
            .filter(models.VendorType.type_id == vendor_type)
            .scalar()
        )

    return {
        "sample_data": False,
        "access_mode": "authenticated",
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "available_start": earliest_date.isoformat(),
            "available_end": latest_date.isoformat(),
        },
        "selected_filters": {
            "vendor_id": vendor_id,
            "vendor_type": vendor_type,
            "vendor_type_name": selected_type,
        },
        "permissions": {"can_view_revenue": can_view_revenue},
        "filter_options": _get_filter_options(db, accessible_vendor_ids),
        "kpis": kpis,
        "demand_trend": trend,
        "demand_heatmap": {
            "days": list(DAY_NAMES),
            "periods": list(TIME_PERIODS),
            "values": heatmap,
        },
        "service_outlook": service_outlook,
        "rush_hour_radar": radar,
        "upcoming_context_events": upcoming_events,
        "privacy_policy": {
            "suppression_threshold": MIN_STUDENTS_THRESHOLD,
            "review_required": False,
            "notice": None,
        },
    }
