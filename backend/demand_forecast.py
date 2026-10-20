from datetime import timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func
import models

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def calculate_demand_forecast(db: Session, vendor_id: int):
    # 1. Fetch vendor to verify it exists
    vendor = db.query(models.Vendor).filter(models.Vendor.vendor_id == vendor_id).first()
    if not vendor:
        return {"error": "Vendor not found"}

    # 2. Query daily transaction totals
    daily_stats = (
        db.query(
            func.date(models.Transaction.datetime).label("txn_date"),
            func.count(models.Transaction.transaction_id).label("order_count"),
            func.sum(models.Transaction.value).label("revenue"),
            func.count(func.distinct(models.Transaction.student_id)).label("customer_count"),
        )
        .filter(models.Transaction.vendor_id == vendor_id)
        .group_by(func.date(models.Transaction.datetime))
        .order_by("txn_date")
        .all()
    )

    if not daily_stats:
        return {"error": "No transaction history for this vendor"}

    # 3. Calculate baseline day-of-week averages
    dow_totals = defaultdict(lambda: {"orders": 0, "revenue": 0.0, "customers": 0, "days": 0})
    for row in daily_stats:
        dow = row.txn_date.weekday()  # 0=Monday ... 6=Sunday
        dow_totals[dow]["orders"] += row.order_count
        dow_totals[dow]["revenue"] += float(row.revenue or 0.0)
        dow_totals[dow]["customers"] += row.customer_count
        dow_totals[dow]["days"] += 1

    dow_avg = {
        d: {
            "orders": v["orders"] / v["days"],
            "revenue": v["revenue"] / v["days"],
            "customers": v["customers"] / v["days"],
        }
        for d, v in dow_totals.items()
    }

    # 4. Trend factor: last 28 days vs full history average
    last_date = max(row.txn_date for row in daily_stats)
    recent_cutoff = last_date - timedelta(days=28)
    recent_rows = [r for r in daily_stats if r.txn_date > recent_cutoff]

    overall_avg_revenue = sum(float(r.revenue or 0) for r in daily_stats) / len(daily_stats)
    recent_avg_revenue = (
        sum(float(r.revenue or 0) for r in recent_rows) / len(recent_rows)
        if recent_rows else overall_avg_revenue
    )

    trend_factor = recent_avg_revenue / overall_avg_revenue if overall_avg_revenue > 0 else 1.0
    trend_factor = max(0.5, min(trend_factor, 1.5))  # Clamp extreme swings

    # 5. Project next 7 days
    points = []
    for i in range(1, 8):
        forecast_date = last_date + timedelta(days=i)
        dow = forecast_date.weekday()
        baseline = dow_avg.get(dow, {"orders": 0, "revenue": 0.0, "customers": 0})

        points.append({
            "date": forecast_date.isoformat(),
            "day_of_week": DAY_NAMES[dow],
            "expected_orders": round(baseline["orders"] * trend_factor),
            "expected_revenue": round(baseline["revenue"] * trend_factor, 2),
            "expected_customers": round(baseline["customers"] * trend_factor),
        })



    # 6. Generate recommendations from the most recent complete week

    days_since_sunday = (last_date.weekday() + 1) % 7
    week_end = last_date - timedelta(days=days_since_sunday)
    week_start = week_end - timedelta(days=6)

    recommendations = []

    previous_rows = [
        row for row in daily_stats
        if row.txn_date < week_start
    ]

    previous_dow_totals = defaultdict(
        lambda: {"orders": 0, "days": 0}
    )

    for row in previous_rows:
        dow = row.txn_date.weekday()
        previous_dow_totals[dow]["orders"] += row.order_count
        previous_dow_totals[dow]["days"] += 1

    previous_dow_avg = {
        dow: totals["orders"] / totals["days"]
        for dow, totals in previous_dow_totals.items()
        if totals["days"] > 0
    }


    for row in daily_stats:
        if not (week_start <= row.txn_date <= week_end):
            continue

        dow = row.txn_date.weekday()
        average_orders = previous_dow_avg.get(dow)

        if average_orders is None or average_orders <= 0:
            continue

        if row.order_count <= average_orders:
            continue

        percentage_above = (
            (row.order_count - average_orders) / average_orders
        ) * 100

        percentage_above = round(percentage_above)

        forecast_point = next(
            (
                point for point in points
                if point["day_of_week"] == DAY_NAMES[dow]
            ),
            None
        )

        if forecast_point is None:
            continue

        if percentage_above >= 50:
            demand_level = "high"
            action = "Consider hosting an event or running a special."
        else:
            demand_level = "above_average"
            action = "Consider offering a discount or running a special."

        recommendations.append({
            "forecast_date": forecast_point["date"],
            "day_of_week": forecast_point["day_of_week"],
            "historical_date": row.txn_date.isoformat(),
            "recommendation": action,
            "demand_level": demand_level,
            "demand_comparison": (
                f"{percentage_above}% above the usual "
                f"{DAY_NAMES[dow]} average"
            ),
        })
   
    return {
        "vendor_id": vendor.vendor_id,
        "vendor_name": vendor.name,
        "history_from": daily_stats[0].txn_date.isoformat(),
        "history_to": last_date.isoformat(),
        "horizon_days": 7,
        "points": points,
        "recommendations": recommendations,
    }

