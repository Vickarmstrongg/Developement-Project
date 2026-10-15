from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import context_events
import dashboard
import database
import models
from access.constants import Role
from access.deps import get_current_user, shape_for_role
from demand_forecast import calculate_demand_forecast
from fair_comparison import calculate_fair_comparison
from privacy import MIN_STUDENTS_THRESHOLD
from rush_hour import get_bulk_vendor_status


router = APIRouter(
    prefix="/api/honest-results",
    tags=["Honest Results Checker"],
    dependencies=[Depends(get_current_user)],
)

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
TIME_PERIODS = (
    (7, 10),
    (10, 12),
    (12, 14),
    (14, 17),
    (17, 20),
    (20, 22),
)
QUIET_THRESHOLD = 0.70
BUSY_THRESHOLD = 1.20
AVERAGE_BAND_PERCENTAGE = 0.10
MIN_PEER_BUSINESSES = 3


class CheckRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    vendor_id: int | None = Field(default=None, gt=0)
    vendor_type: int | None = Field(default=None, gt=0)
    radar_day: int = Field(default=4, ge=0, le=6)
    radar_hour: int = Field(default=12, ge=0, le=23)
    fair_date: date | None = None
    event_year: int | None = Field(default=None, ge=1, le=9999)
    event_type: str | None = None


@router.get("/options")
def get_checker_options(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
) -> dict[str, Any]:
    allowed = accessible_vendor_ids(user)
    options = dashboard._get_filter_options(db, allowed)
    event_types = []
    if user.role == Role.ADMIN.value:
        event_types = context_events.allowed_types(db)
    return {**options, "event_types": event_types}


def validate_request_filters(filters: CheckRequest) -> None:
    if filters.start_date and filters.end_date and filters.start_date > filters.end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")


def accessible_vendor_ids(user: models.User) -> list[int] | None:
    return None if user.all_vendors else user.vendor_ids


def can_view_revenue(user: models.User) -> bool:
    return user.role in {Role.ADMIN.value, Role.MANAGER.value}


def can_view_fair_comparison(user: models.User) -> bool:
    return user.role in {Role.ADMIN.value, Role.MANAGER.value}


def can_view_context_events(user: models.User) -> bool:
    return user.role == Role.ADMIN.value


def validate_vendor_scope(vendor_id: int, user: models.User) -> None:
    allowed = accessible_vendor_ids(user)
    if allowed is not None and vendor_id not in allowed:
        raise HTTPException(status_code=403, detail="You do not have access to this vendor")


def _check(
    check_id: str,
    title: str,
    status: str,
    scope: str,
    application_result: Any = None,
    expected_result: Any = None,
    difference: Any = None,
    explanation: str = "",
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "scope": scope,
        "application_result": application_result,
        "expected_result": expected_result,
        "difference": difference,
        "explanation": explanation,
        "reason": reason,
    }


def compare_values(
    check_id: str,
    title: str,
    scope: str,
    application_result: Any,
    expected_result: Any,
    *,
    no_data: bool = False,
    explanation: str,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    if no_data:
        return _check(
            check_id, title, "NOT CHECKED", scope,
            application_result, expected_result,
            explanation=explanation,
            reason="There is no transaction data in this selection.",
        )

    if isinstance(application_result, (int, float)) and isinstance(expected_result, (int, float)):
        difference = round(float(application_result) - float(expected_result), 4)
        matched = math.isclose(
            float(application_result),
            float(expected_result),
            rel_tol=0,
            abs_tol=tolerance,
        )
    else:
        difference = None if application_result == expected_result else "Mismatch"
        matched = application_result == expected_result

    return _check(
        check_id,
        title,
        "PASS" if matched else "FAIL",
        scope,
        application_result,
        expected_result,
        difference,
        explanation,
    )


def _safe_metric(value: Any, suppressed: bool) -> Any:
    return None if suppressed else value


def _daily_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _transaction_query(
    db: Session,
    start_date: date,
    end_date: date,
    vendor_id: int | None,
    vendor_type: int | None,
    allowed_vendor_ids: list[int] | None,
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
    if allowed_vendor_ids is not None:
        query = query.filter(models.Transaction.vendor_id.in_(allowed_vendor_ids))
    return query


def _status_counts(statuses: dict[int, dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for status in statuses.values():
        key = "suppressed" if status["status"] == "suppressed" else status.get("level", "unavailable")
        counts[key] += 1
    return {
        "vendors": len(statuses),
        "busy": counts["busy"],
        "normal": counts["normal"],
        "quiet": counts["quiet"],
        "suppressed": counts["suppressed"],
        "unavailable": counts["unavailable"],
    }


def _independent_radar_statuses(
    db: Session,
    vendor_ids: list[int],
    day_of_week: int,
    hour: int,
    reference_date: date,
) -> dict[int, dict[str, Any]]:
    days_back = (reference_date.weekday() - day_of_week) % 7
    most_recent = reference_date - timedelta(days=days_back)
    dates = [most_recent - timedelta(weeks=index) for index in range(3, -1, -1)]
    matching_hours = [hour - 1, hour, hour + 1]
    date_counts = {
        (vendor_id, period_date): 0
        for vendor_id in vendor_ids
        for period_date in dates
    }
    rows = (
        db.query(
            models.Transaction.vendor_id,
            func.date(models.Transaction.datetime).label("transaction_date"),
            func.count(models.Transaction.transaction_id).label("transactions"),
        )
        .filter(
            models.Transaction.vendor_id.in_(vendor_ids),
            func.date(models.Transaction.datetime).in_(dates),
            func.extract("hour", models.Transaction.datetime).in_(matching_hours),
        )
        .group_by(models.Transaction.vendor_id, func.date(models.Transaction.datetime))
        .all()
    )
    for row in rows:
        date_counts[(row.vendor_id, _daily_date(row.transaction_date))] = int(row.transactions)

    student_counts = dict(
        db.query(
            models.Transaction.vendor_id,
            func.count(func.distinct(models.Transaction.student_id)),
        )
        .filter(
            models.Transaction.vendor_id.in_(vendor_ids),
            func.date(models.Transaction.datetime).in_(dates),
            func.extract("hour", models.Transaction.datetime).in_(matching_hours),
        )
        .group_by(models.Transaction.vendor_id)
        .all()
    )

    independent = {}
    for vendor_id in vendor_ids:
        student_count = int(student_counts.get(vendor_id, 0))
        if student_count < MIN_STUDENTS_THRESHOLD:
            independent[vendor_id] = {"status": "suppressed", "level": None}
            continue

        prior_average = sum(date_counts[(vendor_id, day)] for day in dates[:3]) / 3
        current_count = date_counts[(vendor_id, dates[-1])]
        if prior_average == 0:
            level = "busy" if current_count > 0 else "normal"
        elif current_count <= prior_average * QUIET_THRESHOLD:
            level = "quiet"
        elif current_count >= prior_average * BUSY_THRESHOLD:
            level = "busy"
        else:
            level = "normal"
        independent[vendor_id] = {"status": "ok", "level": level}
    return independent


def _independent_forecast(daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not daily_rows:
        return []

    last_date = max(row["date"] for row in daily_rows)
    weekday_values: dict[int, list[dict[str, float]]] = defaultdict(list)
    for row in daily_rows:
        weekday_values[row["date"].weekday()].append(row)
    weekday_averages = {
        weekday: {
            key: sum(row[key] for row in rows) / len(rows)
            for key in ("orders", "revenue", "customers")
        }
        for weekday, rows in weekday_values.items()
    }
    recent_cutoff = last_date - timedelta(days=28)
    recent = [row for row in daily_rows if row["date"] > recent_cutoff]
    overall_mean = sum(row["revenue"] for row in daily_rows) / len(daily_rows)
    recent_mean = (
        sum(row["revenue"] for row in recent) / len(recent)
        if recent else overall_mean
    )
    trend = max(0.5, min(recent_mean / overall_mean, 1.5)) if overall_mean > 0 else 1.0

    result = []
    for offset in range(1, 8):
        forecast_date = last_date + timedelta(days=offset)
        averages = weekday_averages.get(
            forecast_date.weekday(),
            {"orders": 0.0, "revenue": 0.0, "customers": 0.0},
        )
        result.append({
            "date": forecast_date.isoformat(),
            "day_of_week": DAY_NAMES[forecast_date.weekday()],
            "expected_orders": round(averages["orders"] * trend),
            "expected_revenue": round(averages["revenue"] * trend, 2),
            "expected_customers": round(averages["customers"] * trend),
        })
    return result


def _forecast_backtest(daily_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not daily_rows:
        return None

    last_date = max(row["date"] for row in daily_rows)
    first_date = min(row["date"] for row in daily_rows)
    actual_by_date = {row["date"]: row for row in daily_rows}
    holdout_start = max(first_date, last_date - timedelta(days=27))
    errors = []
    actual_total = 0
    target_count = 0

    for offset in range((last_date - holdout_start).days + 1):
        target_date = holdout_start + timedelta(days=offset)
        training = [row for row in daily_rows if row["date"] < target_date]
        if len(training) < 28:
            continue
        training_last = max(row["date"] for row in training)
        forecast_date = training_last + timedelta(days=1)
        if forecast_date != target_date:
            continue
        expected_point = _independent_forecast(training)[0]
        actual_orders = actual_by_date.get(target_date, {}).get("orders", 0)
        errors.append(abs(actual_orders - expected_point["expected_orders"]))
        actual_total += actual_orders
        target_count += 1

    if target_count < 7 or actual_total <= 0:
        return None
    return {
        "holdout_days": target_count,
        "mae_transactions": round(sum(errors) / target_count, 3),
        "wape_transactions_percent": round(sum(errors) / actual_total * 100, 2),
        "training_uses_only_prior_dates": True,
    }


def _check_dashboard(
    db: Session,
    user: models.User,
    filters: CheckRequest,
    allowed_vendor_ids: list[int] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    application = dashboard.get_dashboard_overview(
        start_date=filters.start_date,
        end_date=filters.end_date,
        vendor_id=filters.vendor_id,
        vendor_type=filters.vendor_type,
        db=db,
        current_user=user,
    )
    date_range = application["date_range"]
    checks = []
    if not date_range.get("start") or not date_range.get("end"):
        for check_id, title in (
            ("dashboard_transactions", "Dashboard transaction total"),
            ("dashboard_customers", "Dashboard distinct customer count"),
            ("dashboard_daily_trend", "Dashboard daily trend"),
            ("dashboard_heatmap", "Dashboard day/time heatmap"),
        ):
            checks.append(_check(
                check_id, title, "NOT CHECKED", "No available transaction history",
                reason="The selected vendor scope has no transaction history to validate.",
                explanation="No data is not treated as a successful validation.",
            ))
        checks.append(_check(
            "dashboard_revenue", "Dashboard revenue total", "NOT CHECKED",
            "No available transaction history",
            reason="The selected vendor scope has no transaction history to validate.",
            explanation="No data is not treated as a successful validation.",
        ) if user.role != Role.STAFF.value else _check(
            "dashboard_revenue", "Dashboard revenue total", "NOT CHECKED",
            "Role permission",
            reason="Revenue is not available to Staff and was not queried.",
            explanation="The checker does not calculate or return revenue for Staff.",
        ))
        checks.append(compare_values(
            "dashboard_vendor_coverage", "Dashboard vendor coverage", "No transactions",
            application["kpis"]["vendors_covered"], 0,
            explanation="The selected filters contain no vendors with transactions.",
        ))
        return checks, application

    start_date = date.fromisoformat(date_range["start"])
    end_date = date.fromisoformat(date_range["end"])
    base = _transaction_query(
        db, start_date, end_date, filters.vendor_id, filters.vendor_type, allowed_vendor_ids,
    )
    fields = [
        func.count(models.Transaction.transaction_id).label("transactions"),
        func.count(func.distinct(models.Transaction.student_id)).label("students"),
        func.count(func.distinct(models.Transaction.vendor_id)).label("vendors"),
    ]
    revenue_allowed = can_view_revenue(user)
    if revenue_allowed:
        fields.append(func.sum(models.Transaction.value).label("revenue"))
    aggregate = base.with_entities(*fields).one()
    has_data = int(aggregate.transactions) > 0
    suppressed = has_data and int(aggregate.students) < MIN_STUDENTS_THRESHOLD
    kpis = application["kpis"]
    safe_transactions = _safe_metric(int(aggregate.transactions), suppressed)
    safe_customers = _safe_metric(int(aggregate.students), suppressed)
    safe_revenue = (
        _safe_metric(float(aggregate.revenue or 0), suppressed)
        if revenue_allowed else None
    )

    for metric_id, title, actual, expected in (
        ("dashboard_transactions", "Dashboard transaction total", kpis["total_transactions"], safe_transactions),
        ("dashboard_customers", "Dashboard distinct customer count", kpis["distinct_customers"], safe_customers),
    ):
        if not has_data:
            checks.append(_check(
                metric_id, title, "NOT CHECKED", f"{start_date} to {end_date}",
                actual, expected,
                explanation="No transaction totals exist for this selection.",
                reason="The selection contains no transaction records.",
            ))
        elif suppressed:
            checks.append(compare_values(
                metric_id, title, f"{start_date} to {end_date}",
                actual, expected,
                explanation="Both the application and independent query must suppress the aggregate below the configured privacy threshold.",
            ))
        else:
            checks.append(compare_values(
                metric_id, title, f"{start_date} to {end_date}",
                actual, expected,
                explanation="Compared the displayed aggregate with a separate SQL count over the same date and vendor filters.",
            ))

    if not revenue_allowed:
        checks.append(_check(
            "dashboard_revenue", "Dashboard revenue total", "NOT CHECKED",
            f"{start_date} to {end_date}",
            reason="Revenue is not available to Staff and was not queried.",
            explanation="The checker does not calculate or return revenue for Staff.",
        ))
    elif not has_data:
        checks.append(_check(
            "dashboard_revenue", "Dashboard revenue total", "NOT CHECKED",
            f"{start_date} to {end_date}",
            reason="The selection contains no transaction records.",
            explanation="No revenue total exists for this selection.",
        ))
    else:
        checks.append(compare_values(
            "dashboard_revenue", "Dashboard revenue total",
            f"{start_date} to {end_date}", kpis.get("revenue"), safe_revenue,
            explanation="Compared the displayed permitted revenue with an independent SQL sum.",
        ))

    checks.append(compare_values(
        "dashboard_vendor_coverage", "Dashboard vendor coverage",
        f"{start_date} to {end_date}",
        kpis["vendors_covered"], int(aggregate.vendors),
        explanation="Counts distinct vendors with matching transactions; this metric is not privacy-suppressed by the current dashboard.",
    ))

    trend_fields = [
        func.date(models.Transaction.datetime).label("day"),
        func.count(models.Transaction.transaction_id).label("transactions"),
        func.count(func.distinct(models.Transaction.student_id)).label("students"),
    ]
    if revenue_allowed:
        trend_fields.append(func.sum(models.Transaction.value).label("revenue"))
    daily_rows = (
        base.with_entities(*trend_fields)
        .group_by(func.date(models.Transaction.datetime))
        .order_by(func.date(models.Transaction.datetime))
        .all()
    )
    expected_trend = []
    for row in daily_rows:
        day_suppressed = int(row.students) < MIN_STUDENTS_THRESHOLD
        expected_trend.append({
            "date": _daily_date(row.day).isoformat(),
            "transactions": None if day_suppressed else int(row.transactions),
            "status": "suppressed" if day_suppressed else "available",
            **({
                "revenue": None if day_suppressed else float(row.revenue or 0)
            } if revenue_allowed else {}),
        })
    actual_trend = application["demand_trend"]
    trend_matches = actual_trend == expected_trend
    trend_mismatches = sum(
        actual != expected
        for actual, expected in zip(actual_trend, expected_trend)
    ) + abs(len(actual_trend) - len(expected_trend))
    checks.append(_check(
        "dashboard_daily_trend",
        "Dashboard daily transaction trend",
        "NOT CHECKED" if not daily_rows else ("PASS" if trend_matches else "FAIL"),
        f"{start_date} to {end_date}",
        f"{len(actual_trend)} daily points",
        f"{len(expected_trend)} independently grouped daily points",
        trend_mismatches,
        "Compared each displayed date, transaction count, and privacy-suppression state with independent daily SQL aggregates.",
        None if daily_rows else "The selection contains no daily transaction records.",
    ))

    heatmap_days = application["demand_heatmap"]["values"]
    heatmap_actual = [
        (day["day"], index, cell["status"], cell["transactions"])
        for day in heatmap_days
        for index, cell in enumerate(day["cells"])
    ]
    hour = func.extract("hour", models.Transaction.datetime)
    weekday = func.extract("isodow", models.Transaction.datetime) - 1
    period_case = case(
        *((((hour >= begin) & (hour < finish)), index)
          for index, (begin, finish) in enumerate(TIME_PERIODS)),
        else_=None,
    )
    cell_rows = (
        base.with_entities(
            weekday.label("weekday"),
            period_case.label("period"),
            func.count(models.Transaction.transaction_id).label("transactions"),
            func.count(func.distinct(models.Transaction.student_id)).label("students"),
        )
        .filter(period_case.is_not(None))
        .group_by(weekday, period_case)
        .all()
    )
    expected_cells = {}
    for row in cell_rows:
        day_index = int(row.weekday)
        period_index = int(row.period)
        is_hidden = int(row.students) < MIN_STUDENTS_THRESHOLD
        expected_cells[(day_index, period_index)] = (
            "suppressed" if is_hidden else "available",
            None if is_hidden else int(row.transactions),
        )
    expected_heatmap = [
        (
            DAY_NAMES[day_index],
            period_index,
            *expected_cells.get((day_index, period_index), ("no_data", None)),
        )
        for day_index in range(7)
        for period_index in range(len(TIME_PERIODS))
    ]
    mismatched_cells = sum(
        actual != expected
        for actual, expected in zip(heatmap_actual, expected_heatmap)
    ) + abs(len(heatmap_actual) - len(expected_heatmap))
    checks.append(_check(
        "dashboard_heatmap",
        "Dashboard weekday/time heatmap",
        "PASS" if heatmap_actual == expected_heatmap else "FAIL",
        f"{start_date} to {end_date}",
        f"{len(heatmap_actual)} displayed cells",
        f"{len(expected_heatmap)} independently grouped cells",
        mismatched_cells,
        "Compared all seven weekday by six time-period cells, including no-data and privacy-suppressed cells.",
    ))

    suppressed_days = sum(point["status"] == "suppressed" for point in expected_trend)
    if not has_data:
        checks.append(_check(
            "dashboard_trend_total_consistency",
            "Dashboard summary vs visible trend total",
            "NOT CHECKED",
            f"{start_date} to {end_date}",
            "No displayed transaction total",
            "No daily transaction points to reconcile",
            explanation="The selected filters contain no transactions; no summary-to-chart consistency claim can be made.",
            reason="No transaction data is available for this vendor/date selection.",
        ))
    elif suppressed_days:
        checks.append(_check(
            "dashboard_trend_total_consistency",
            "Dashboard summary vs visible trend total",
            "WARNING",
            f"{start_date} to {end_date}",
            "Daily chart contains privacy-suppressed points",
            "Not safely comparable by summing visible points",
            explanation="Some daily values are suppressed, so the visible chart cannot be summed to reconstruct the summary without weakening privacy.",
            reason=f"{suppressed_days} daily point(s) are suppressed.",
        ))
    else:
        visible_total = sum(point["transactions"] for point in expected_trend)
        checks.append(compare_values(
            "dashboard_trend_total_consistency",
            "Dashboard summary vs daily trend total",
            f"{start_date} to {end_date}",
            kpis["total_transactions"],
            visible_total,
            explanation="Compared the summary transaction total with the sum of all unsuppressed daily chart values.",
        ))
    return checks, application


def _check_forecast(
    db: Session,
    user: models.User,
    vendor_id: int | None,
    allowed_vendor_ids: list[int] | None,
) -> list[dict[str, Any]]:
    scope = f"Vendor {vendor_id}" if vendor_id is not None else "No vendor selected"
    if vendor_id is None:
        return [
            _check(
                "forecast_horizon", "Demand forecast dates and horizon", "NOT CHECKED", scope,
                explanation="The forecast is calculated for one vendor at a time.",
                reason="Select an accessible vendor to validate the forecast.",
            ),
            _check(
                "forecast_backtest", "Historical forecast backtest", "NOT CHECKED", scope,
                explanation="Backtesting requires a selected vendor and sufficient history.",
                reason="Select an accessible vendor to validate the forecast.",
            ),
        ]
    validate_vendor_scope(vendor_id, user)
    forecast = shape_for_role(user, calculate_demand_forecast(db, vendor_id))
    if forecast.get("error"):
        return [
            _check(
                "forecast_horizon", "Demand forecast dates and horizon", scope=scope,
                status="NOT CHECKED", application_result=forecast["error"],
                explanation="The production forecast is unavailable for this vendor.",
                reason=forecast["error"],
            ),
            _check(
                "forecast_backtest", "Historical forecast backtest", "NOT CHECKED", scope,
                explanation="No production forecast is available to validate.",
                reason=forecast["error"],
            ),
        ]

    tx_scope = db.query(models.Transaction).filter(models.Transaction.vendor_id == vendor_id)
    daily_query = (
        tx_scope.with_entities(
            func.date(models.Transaction.datetime).label("day"),
            func.count(models.Transaction.transaction_id).label("orders"),
            func.sum(models.Transaction.value).label("revenue"),
            func.count(func.distinct(models.Transaction.student_id)).label("customers"),
        )
        .group_by(func.date(models.Transaction.datetime))
        .order_by(func.date(models.Transaction.datetime))
    )
    daily_rows = [
        {
            "date": _daily_date(row.day),
            "orders": int(row.orders),
            "revenue": float(row.revenue or 0),
            "customers": int(row.customers),
        }
        for row in daily_query.all()
    ]
    expected_points = _independent_forecast(daily_rows)
    if user.role == Role.STAFF.value:
        expected_points = shape_for_role(user, {"points": expected_points})["points"]
    actual_points = forecast.get("points", [])
    expected_dates = [point["date"] for point in expected_points]
    actual_dates = [point.get("date") for point in actual_points]
    dates_valid = (
        len(actual_points) == 7
        and actual_dates == expected_dates
        and forecast.get("horizon_days") == 7
        and len(set(actual_dates)) == 7
    )
    checks = [
        _check(
            "forecast_horizon",
            "Demand forecast dates and horizon",
            "PASS" if dates_valid else "FAIL",
            f"{forecast.get('history_from')} to {forecast.get('history_to')}",
            {"horizon_days": forecast.get("horizon_days"), "dates": actual_dates},
            {"horizon_days": 7, "dates": expected_dates},
            0 if dates_valid else abs(7 - len(actual_points)),
            "The expected horizon is seven consecutive dates after the latest transaction date in the selected vendor's history.",
        )
    ]
    numeric_valid = True
    for point in actual_points:
        for key in ("expected_orders", "expected_customers"):
            value = point.get(key)
            numeric_valid &= isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
        if user.role != Role.STAFF.value:
            value = point.get("expected_revenue")
            numeric_valid &= isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
    formula_matches = actual_points == expected_points
    checks.append(_check(
        "forecast_calculation",
        "Demand forecast values and calculation",
        "PASS" if numeric_valid and formula_matches else "FAIL",
        f"Vendor {vendor_id}; seven-day forecast",
        "Forecast output matches independently recomputed weekday averages and clamped trend factor" if formula_matches else "Forecast differs from independent recomputation",
        "Seven independently calculated daily values; all finite and non-negative",
        0 if formula_matches else "Value or shape mismatch",
        "Recomputed the existing implementation from grouped daily history. Revenue fields are excluded from Staff validation results.",
    ))

    backtest = _forecast_backtest(daily_rows)
    if backtest is None:
        checks.append(_check(
            "forecast_backtest",
            "Historical forecast backtest",
            "NOT CHECKED",
            f"Vendor {vendor_id}",
            explanation="A historical error metric is not evidence of future accuracy.",
            reason="Fewer than seven leakage-free holdout days with at least 28 prior observed days, or no actual transaction volume, were available.",
        ))
    else:
        checks.append(_check(
            "forecast_backtest",
            "Historical forecast backtest",
            "WARNING",
            f"Vendor {vendor_id}; {backtest['holdout_days']} holdout days",
            {"mae_transactions": backtest["mae_transactions"]},
            {"wape_transactions_percent": backtest["wape_transactions_percent"]},
            None,
            "Historical one-day-ahead backtest uses only transaction dates strictly before each target date. Metrics describe this historical sample, not future accuracy.",
            "The current model is a weekday-average daily forecast; performance may differ on future periods.",
        ))

    checks.append(_check(
        "forecast_product_scope",
        "Forecast scope vs project concept",
        "WARNING",
        f"Vendor {vendor_id}",
        "Seven daily forecasts",
        "The concept note describes hourly demand across 24 hours.",
        explanation="This checker validates the implemented seven-day daily forecast; it does not treat that as confirmation of the product-level hourly forecasting requirement.",
        reason="Confirm the intended forecast granularity with the product owner/team.",
    ))
    return checks


def _check_radar(
    db: Session,
    user: models.User,
    filters: CheckRequest,
    allowed_vendor_ids: list[int] | None,
) -> dict[str, Any]:
    query = db.query(models.Vendor.vendor_id)
    if filters.vendor_type is not None:
        query = query.filter(models.Vendor.type_id == filters.vendor_type)
    if filters.vendor_id is not None:
        validate_vendor_scope(filters.vendor_id, user)
        query = query.filter(models.Vendor.vendor_id == filters.vendor_id)
    if allowed_vendor_ids is not None:
        query = query.filter(models.Vendor.vendor_id.in_(allowed_vendor_ids))
    vendor_ids = [row[0] for row in query.order_by(models.Vendor.vendor_id).all()]
    latest = db.query(func.max(models.Transaction.datetime)).scalar()
    scope = (
        f"{DAY_NAMES[filters.radar_day]}, hour {filters.radar_hour}; "
        f"{len(vendor_ids)} accessible vendor(s)"
    )
    if latest is None or not vendor_ids:
        return _check(
            "radar_statuses",
            "Rush Hour Radar historical status",
            "NOT CHECKED",
            scope,
            explanation="Radar statuses require a reference date and accessible vendors.",
            reason="No matching vendor transaction history exists.",
        )
    reference_date = _daily_date(latest)
    app_statuses = get_bulk_vendor_status(
        db, vendor_ids, filters.radar_day, filters.radar_hour, reference_date,
    )
    expected_statuses = _independent_radar_statuses(
        db, vendor_ids, filters.radar_day, filters.radar_hour, reference_date,
    )
    app_summary = _status_counts(app_statuses)
    expected_summary = _status_counts(expected_statuses)
    mismatches = sum(
        (
            app_statuses[vendor_id].get("status") != expected_statuses[vendor_id].get("status")
            or app_statuses[vendor_id].get("level") != expected_statuses[vendor_id].get("level")
        )
        for vendor_id in vendor_ids
    )
    return _check(
        "radar_statuses",
        "Rush Hour Radar historical status",
        "PASS" if mismatches == 0 else "FAIL",
        scope,
        {"reference_date": reference_date.isoformat(), **app_summary},
        {"reference_date": reference_date.isoformat(), **expected_summary},
        mismatches,
        "Independently recalculated each selected vendor's latest matching weekday occurrence against the prior three weekly occurrences, using the existing one-hour-neighbour window and privacy rule. Individual student counts are not returned.",
    )


def _check_fair_comparison(
    db: Session,
    user: models.User,
    vendor_id: int | None,
    fair_date: date | None,
) -> list[dict[str, Any]]:
    if not can_view_fair_comparison(user):
        return [
            _check(
                "fair_comparison_integrity",
                "Fair Comparison calculation",
                "NOT CHECKED",
                "Role permission",
                explanation="Fair Comparison remains restricted to Admin and Manager.",
                reason="This user's role is not permitted to access Fair Comparison results.",
            ),
            _check(
                "fair_comparison_business_rule",
                "Fair Comparison business-rule alignment",
                "NOT CHECKED",
                "Product specification",
                explanation="The implementation and concept note use different peer minimums, and the concept note does not define the current ±10% category formula.",
                reason="Admin/Manager-only check; no restricted comparison values were queried.",
            ),
        ]
    if vendor_id is None:
        return [
            _check(
                "fair_comparison_integrity",
                "Fair Comparison calculation",
                "NOT CHECKED",
                "No vendor selected",
                explanation="The comparison API requires a selected vendor.",
                reason="Select an accessible vendor.",
            ),
            _check(
                "fair_comparison_business_rule",
                "Fair Comparison business-rule alignment",
                "NOT CHECKED",
                "Product specification",
                explanation="The current peer minimum and category formula require product-owner confirmation.",
                reason="Select an accessible vendor and confirm the business rule.",
            ),
        ]
    validate_vendor_scope(vendor_id, user)
    shown = calculate_fair_comparison(db, vendor_id, fair_date)
    if shown.get("status") != "ok":
        expected_suppressed_size = None
        if shown.get("status") == "suppressed":
            vendor = db.query(models.Vendor).filter(
                models.Vendor.vendor_id == vendor_id
            ).first()
            if vendor:
                same_type_ids = [
                    row[0] for row in db.query(models.Vendor.vendor_id)
                    .filter(models.Vendor.type_id == vendor.type_id).all()
                ]
                historical_counts = dict(
                    db.query(
                        models.Transaction.vendor_id,
                        func.count(models.Transaction.transaction_id),
                    )
                    .filter(models.Transaction.vendor_id.in_(same_type_ids))
                    .group_by(models.Transaction.vendor_id)
                    .all()
                )

                def peer_tier(count: int) -> str:
                    return "small" if count < 1500 else "medium" if count < 3000 else "large"

                target_tier = peer_tier(int(historical_counts.get(vendor_id, 0)))
                peer_ids = [
                    peer_id for peer_id in same_type_ids
                    if peer_tier(int(historical_counts.get(peer_id, 0))) == target_tier
                ]
                if len(peer_ids) < MIN_PEER_BUSINESSES:
                    expected_suppressed_size = len(peer_ids)
                else:
                    latest_day = db.query(
                        func.max(func.date(models.Transaction.datetime))
                    ).scalar()
                    if fair_date is not None:
                        period_start = period_end = fair_date
                    elif latest_day is not None:
                        period_end = _daily_date(latest_day)
                        period_start = period_end - timedelta(days=6)
                    else:
                        period_start = period_end = None
                    if period_start is not None:
                        participating = (
                            db.query(models.Transaction.vendor_id)
                            .filter(
                                models.Transaction.vendor_id.in_(peer_ids),
                                func.date(models.Transaction.datetime) >= period_start,
                                func.date(models.Transaction.datetime) <= period_end,
                            )
                            .group_by(models.Transaction.vendor_id)
                            .count()
                        )
                        if participating < MIN_PEER_BUSINESSES:
                            expected_suppressed_size = participating
        if expected_suppressed_size is not None:
            suppression_matches = shown.get("peer_group_size") == expected_suppressed_size
            return [
                _check(
                    "fair_comparison_integrity",
                    "Fair Comparison insufficient-peer suppression",
                    "PASS" if suppression_matches else "FAIL",
                    f"Vendor {vendor_id}",
                    {
                        "status": shown.get("status"),
                        "participating_businesses": shown.get("peer_group_size"),
                    },
                    {
                        "status": "suppressed",
                        "participating_businesses": expected_suppressed_size,
                    },
                    0 if suppression_matches else "Mismatch",
                    "Independently counted the type-and-size cohort and participating businesses without returning peer identities or individual figures.",
                ),
                _check(
                    "fair_comparison_business_rule",
                    "Fair Comparison business-rule alignment",
                    "NOT CHECKED",
                    "Product specification",
                    explanation="The current suppression behavior can be checked against the implementation, but the intended peer minimum still conflicts with the concept note.",
                    reason="The concept note calls for at least four other businesses, while the implementation minimum is three businesses total.",
                ),
            ]
        return [
            _check(
                "fair_comparison_integrity",
                "Fair Comparison calculation",
                "NOT CHECKED",
                f"Vendor {vendor_id}",
                shown.get("status", shown.get("error")),
                explanation="The comparison is unavailable or privacy-suppressed.",
                reason=shown.get("reason", shown.get("error", "No comparison was returned.")),
            ),
            _check(
                "fair_comparison_business_rule",
                "Fair Comparison business-rule alignment",
                "NOT CHECKED",
                "Product specification",
                explanation="No displayed score can be checked against the unsettled product definition.",
                reason="The comparison is unavailable.",
            ),
        ]

    start = date.fromisoformat(shown["period"]["start_date"])
    end = date.fromisoformat(shown["period"]["end_date"])
    vendor = db.query(models.Vendor).filter(models.Vendor.vendor_id == vendor_id).first()
    type_vendor_rows = db.query(models.Vendor.vendor_id).filter(
        models.Vendor.type_id == vendor.type_id
    ).all()
    type_vendor_ids = [row[0] for row in type_vendor_rows]
    all_time_counts = dict(
        db.query(
            models.Transaction.vendor_id,
            func.count(models.Transaction.transaction_id),
        )
        .filter(models.Transaction.vendor_id.in_(type_vendor_ids))
        .group_by(models.Transaction.vendor_id)
        .all()
    )

    def tier(count: int) -> str:
        return "small" if count < 1500 else "medium" if count < 3000 else "large"

    target_tier = tier(int(all_time_counts.get(vendor_id, 0)))
    peer_ids = [
        peer_id for peer_id in type_vendor_ids
        if tier(int(all_time_counts.get(peer_id, 0))) == target_tier
    ]
    period_rows = (
        db.query(
            models.Transaction.vendor_id,
            func.count(models.Transaction.transaction_id).label("transactions"),
            func.sum(models.Transaction.value).label("revenue"),
        )
        .filter(
            models.Transaction.vendor_id.in_(peer_ids),
            func.date(models.Transaction.datetime) >= start,
            func.date(models.Transaction.datetime) <= end,
        )
        .group_by(models.Transaction.vendor_id)
        .all()
    )
    if len(period_rows) < MIN_PEER_BUSINESSES:
        return [
            _check(
                "fair_comparison_integrity",
                "Fair Comparison calculation",
                "FAIL",
                f"Vendor {vendor_id}; {start} to {end}",
                f"{len(period_rows)} participating business(es)",
                f"At least {MIN_PEER_BUSINESSES} participating businesses",
                explanation="The API returned an available comparison despite fewer than its implemented minimum number of participating businesses.",
            ),
            _check(
                "fair_comparison_business_rule",
                "Fair Comparison business-rule alignment",
                "NOT CHECKED",
                "Product specification",
                explanation="Product-level peer minimum and formula remain unconfirmed.",
                reason="The returned peer cohort is below the implementation's minimum.",
            ),
        ]

    target_row = next((row for row in period_rows if row.vendor_id == vendor_id), None)
    vendor_transactions = int(target_row.transactions) if target_row else 0
    peer_average = round(sum(int(row.transactions) for row in period_rows) / len(period_rows), 1)
    vendor_revenue = round(float(target_row.revenue or 0), 2) if target_row else 0
    peer_average_revenue = round(
        sum(float(row.revenue or 0) for row in period_rows) / len(period_rows),
        2,
    )
    if peer_average > 0:
        ratio = vendor_transactions / peer_average
        expected_label = (
            "above_average" if ratio > (1 + AVERAGE_BAND_PERCENTAGE)
            else "below_average" if ratio < (1 - AVERAGE_BAND_PERCENTAGE)
            else "average"
        )
    else:
        expected_label = "average"
    app_metrics = shown.get("metrics", {})
    shown_peer_average = app_metrics.get("peer_average_transactions")
    shown_peer_revenue = app_metrics.get("peer_average_revenue")
    matched = (
        app_metrics.get("vendor_transactions") == vendor_transactions
        and isinstance(shown_peer_average, (int, float))
        and math.isclose(
            float(shown_peer_average),
            peer_average,
            abs_tol=0.01,
        )
        and app_metrics.get("vendor_revenue") == vendor_revenue
        and isinstance(shown_peer_revenue, (int, float))
        and math.isclose(float(shown_peer_revenue), peer_average_revenue, abs_tol=0.01)
        and app_metrics.get("comparison_result") == expected_label
        and shown.get("peer_group", {}).get("participating_businesses") == len(period_rows)
    )
    daily_rows = (
        db.query(
            func.date(models.Transaction.datetime).label("transaction_date"),
            models.Transaction.vendor_id,
            func.count(models.Transaction.transaction_id).label("transactions"),
        )
        .filter(
            models.Transaction.vendor_id.in_(peer_ids),
            func.date(models.Transaction.datetime) >= start,
            func.date(models.Transaction.datetime) <= end,
        )
        .group_by(func.date(models.Transaction.datetime), models.Transaction.vendor_id)
        .all()
    )
    daily_counts = {
        (_daily_date(row.transaction_date).isoformat(), row.vendor_id): int(row.transactions)
        for row in daily_rows
    }
    expected_daily_trend = []
    current_day = start
    while current_day <= end:
        day_key = current_day.isoformat()
        peer_total = sum(daily_counts.get((day_key, peer_id), 0) for peer_id in peer_ids)
        expected_daily_trend.append({
            "date": day_key,
            "vendor_transactions": daily_counts.get((day_key, vendor_id), 0),
            "peer_average_transactions": round(peer_total / len(period_rows), 1),
        })
        current_day += timedelta(days=1)
    actual_daily_trend = shown.get("daily_trend", [])
    daily_matches = actual_daily_trend == expected_daily_trend
    checks = [
        _check(
            "fair_comparison_integrity",
            "Fair Comparison calculation against current implementation",
            "PASS" if matched else "FAIL",
            f"Vendor {vendor_id}; {start} to {end}",
            {
                "vendor_transactions": app_metrics.get("vendor_transactions"),
                "vendor_revenue": app_metrics.get("vendor_revenue"),
                "peer_average_transactions": app_metrics.get("peer_average_transactions"),
                "peer_average_revenue": app_metrics.get("peer_average_revenue"),
                "comparison_result": app_metrics.get("comparison_result"),
                "participating_businesses": shown.get("peer_group", {}).get("participating_businesses"),
            },
            {
                "vendor_transactions": vendor_transactions,
                "vendor_revenue": vendor_revenue,
                "peer_average_transactions": peer_average,
                "peer_average_revenue": peer_average_revenue,
                "comparison_result": expected_label,
                "participating_businesses": len(period_rows),
            },
            None if matched else "Mismatch",
            "Recomputed the current code's all-time volume tier, selected-period transaction aggregates, peer mean, and ±10% classification without exposing peer names or individual peer metrics.",
        ),
        _check(
            "fair_comparison_trend",
            "Fair Comparison daily trend",
            "PASS" if daily_matches else "FAIL",
            f"Vendor {vendor_id}; {start} to {end}",
            f"{len(actual_daily_trend)} daily points",
            f"{len(expected_daily_trend)} independently grouped daily points",
            sum(a != e for a, e in zip(actual_daily_trend, expected_daily_trend))
            + abs(len(actual_daily_trend) - len(expected_daily_trend)),
            "Compared the selected vendor's daily transaction counts and the anonymized peer average with independent grouped database values.",
        ),
        _check(
            "fair_comparison_business_rule",
            "Fair Comparison business-rule alignment",
            "NOT CHECKED",
            f"Vendor {vendor_id}; {start} to {end}",
            "Current implementation uses three participating businesses total and an above/average/below category within ±10%.",
            "The concept note calls for at least four other businesses; it does not define this category formula or a numeric score.",
            explanation="The result can be independently reproduced from code, but compliance with the product definition cannot be established.",
            reason="Product owner/team confirmation is required before this can receive PASS.",
        ),
    ]
    return checks


def _check_events(
    db: Session,
    user: models.User,
    filters: CheckRequest,
) -> list[dict[str, Any]]:
    if not can_view_context_events(user):
        return [
            _check(
                "context_events_api",
                "Context Events API records and filters",
                "NOT CHECKED",
                "Role permission",
                explanation="The Context/Events page is available only to Admin under current frontend permissions.",
                reason="No event records were queried for this role.",
            ),
            _check(
                "context_events_integrity",
                "Context Events dates and source identifiers",
                "NOT CHECKED",
                "Role permission",
                explanation="Event integrity details are not returned outside the page's existing Admin visibility.",
                reason="No event records were queried for this role.",
            ),
            _check(
                "context_events_views",
                "Context Events list/calendar view consistency",
                "NOT CHECKED",
                "Browser rendering",
                explanation="The API checker cannot observe rendered browser state.",
                reason="Run the page in an authenticated browser to verify both visual views.",
            ),
        ]

    query = db.query(models.ContextualEvent)
    if filters.event_year is not None:
        query = query.filter(
            models.ContextualEvent.start_date <= date(filters.event_year, 12, 31),
            models.ContextualEvent.end_date >= date(filters.event_year, 1, 1),
        )
    if filters.event_type:
        query = query.filter(models.ContextualEvent.event_type == filters.event_type)
    rows = query.order_by(
        models.ContextualEvent.start_date, models.ContextualEvent.event_id
    ).all()

    global_query = db.query(models.ContextualEvent)
    invalid_dates = global_query.filter(
        (models.ContextualEvent.start_date.is_(None))
        | (models.ContextualEvent.end_date.is_(None))
        | (models.ContextualEvent.start_date > models.ContextualEvent.end_date)
    ).count()
    duplicate_sources = (
        db.query(models.ContextualEvent.source_context_id)
        .filter(models.ContextualEvent.source_context_id.is_not(None))
        .group_by(models.ContextualEvent.source_context_id)
        .having(func.count(models.ContextualEvent.event_id) > 1)
        .count()
    )
    scope = (
        f"Year {filters.event_year or 'all'}; "
        f"event type {filters.event_type or 'all'}"
    )
    if invalid_dates:
        api_check = _check(
            "context_events_api",
            "Context Events API records and filters",
            "FAIL",
            scope,
            "The event list API cannot serialize all stored date bounds.",
            f"{len(rows)} filtered database row(s)",
            invalid_dates,
            "The API requires valid start and end dates for every returned event.",
            f"{invalid_dates} event record(s) have missing or reversed date bounds.",
        )
    else:
        response = context_events.list_events(
            year=filters.event_year,
            event_type=filters.event_type,
            db=db,
        )
        api_map = {
            item["event_id"]: (
                item["start_date"], item["end_date"], item["event_type"]
            )
            for item in response["events"]
        }
        expected_map = {
            row.event_id: (row.start_date.isoformat(), row.end_date.isoformat(), row.event_type)
            for row in rows
        }
        mismatches = sum(
            api_map.get(event_id) != expected_map.get(event_id)
            for event_id in set(api_map) | set(expected_map)
        )
        api_check = _check(
            "context_events_api",
            "Context Events API records and filters",
            "PASS" if response["count"] == len(rows) and mismatches == 0 else "FAIL",
            scope,
            {"api_count": response["count"], "unique_event_ids": len(api_map)},
            {"database_count": len(rows), "unique_event_ids": len(expected_map)},
            mismatches,
            "Compared the filtered API result against direct database records, including dates, event types, and unique event IDs; event names and creator IDs are not returned.",
        )
    source_total = db.query(models.ContextualEvent.event_id).count()
    duplicate_check = _check(
        "context_events_integrity",
        "Context Events dates and source identifiers",
        "PASS" if invalid_dates == 0 and duplicate_sources == 0 else "FAIL",
        "All stored events",
        {"invalid_date_records": invalid_dates, "duplicate_non_null_source_ids": duplicate_sources},
        {"invalid_date_records": 0, "duplicate_non_null_source_ids": 0},
        invalid_dates + duplicate_sources,
        f"Checked {source_total} event records. No event data was changed.",
    )
    return [
        api_check,
        duplicate_check,
        _check(
            "context_events_views",
            "Context Events list/calendar view consistency",
            "NOT CHECKED",
            scope,
            explanation="The server confirms the filtered API records, but cannot observe whether a browser rendered the same event cards in list and calendar modes.",
            reason="Browser rendering is not observable by this API check.",
        ),
    ]


@router.post("/run")
def run_honest_results(
    filters: CheckRequest,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
) -> dict[str, Any]:
    validate_request_filters(filters)
    allowed = accessible_vendor_ids(user)
    if filters.vendor_id is not None:
        validate_vendor_scope(filters.vendor_id, user)

    if filters.vendor_type is not None:
        exists = db.query(models.VendorType.type_id).filter(
            models.VendorType.type_id == filters.vendor_type
        ).first()
        if exists is None:
            raise HTTPException(status_code=422, detail="Unknown vendor type")
    if filters.vendor_id is not None:
        vendor_query = db.query(models.Vendor.vendor_id).filter(
            models.Vendor.vendor_id == filters.vendor_id
        )
        if allowed is not None:
            vendor_query = vendor_query.filter(models.Vendor.vendor_id.in_(allowed))
        if vendor_query.first() is None:
            raise HTTPException(status_code=404, detail="Vendor not found")
    if filters.event_type and user.role == Role.ADMIN.value:
        if filters.event_type not in context_events.allowed_types(db):
            raise HTTPException(status_code=422, detail="Unknown event type")

    try:
        dashboard_checks, dashboard_result = _check_dashboard(db, user, filters, allowed)
        checks = dashboard_checks
        checks.extend(_check_forecast(db, user, filters.vendor_id, allowed))
        checks.append(_check_radar(db, user, filters, allowed))
        checks.extend(_check_fair_comparison(db, user, filters.vendor_id, filters.fair_date))
        checks.extend(_check_events(db, user, filters))
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Validation could not complete because the database query failed.",
        ) from exc

    checks.append(_check(
        "privacy_threshold_specification",
        "Privacy threshold specification alignment",
        "WARNING",
        "Project concept note vs current runtime policy",
        f"Runtime code suppresses below {MIN_STUDENTS_THRESHOLD} distinct students.",
        "The concept note says at least 10 students or orders.",
        explanation="The checker evaluates operational suppression against the existing code threshold and does not change it.",
        reason="The product owner/team must confirm whether the original concept-note threshold or the later five-student decision is authoritative.",
    ))

    counts = Counter(check["status"] for check in checks)
    all_pass = bool(checks) and counts["PASS"] == len(checks)
    summary = {
        "pass": counts["PASS"],
        "fail": counts["FAIL"],
        "warning": counts["WARNING"],
        "not_checked": counts["NOT CHECKED"],
        "overall_status": (
            "PASS" if all_pass
            else "FAIL" if counts["FAIL"]
            else "REVIEW REQUIRED"
        ),
        "fully_passed": all_pass,
    }
    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "start_date": dashboard_result["date_range"].get("start"),
            "end_date": dashboard_result["date_range"].get("end"),
            "vendor_id": filters.vendor_id,
            "vendor_type": filters.vendor_type,
            "radar_day": filters.radar_day,
            "radar_hour": filters.radar_hour,
            "fair_date": filters.fair_date.isoformat() if filters.fair_date else None,
            "event_year": filters.event_year,
            "event_type": filters.event_type,
        },
        "filter_options": dashboard_result.get("filter_options", {"vendor_types": [], "vendors": []}),
        "summary": summary,
        "checks": checks,
        "privacy_policy": {
            "runtime_threshold": MIN_STUDENTS_THRESHOLD,
            "threshold_is_changed": False,
            "revenue_available": can_view_revenue(user),
            "vendor_scope": "all vendors" if allowed is None else "assigned vendors only",
        },
    }
