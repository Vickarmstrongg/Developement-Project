from sqlalchemy import func
from datetime import timedelta
import models
from privacy import is_suppressed
import re

def parse_gps(gps_str):
    """Parses a WKT 'POINT(longitude latitude)' string into (lat, lon) floats."""
    if not gps_str:
        return None, None
    match = re.match(r"POINT\(([-\d.]+)\s+([-\d.]+)\)", gps_str)
    if not match:
        return None, None
    lon, lat = match.groups()
    return float(lat), float(lon)

QUIET_THRESHOLD = 0.70   # 30% below baseline
BUSY_THRESHOLD = 1.20    # 20% above baseline


def get_reference_date(db):
    """Use the latest date in the data as 'today', since this is historical synthetic data."""
    latest = db.query(func.max(models.Transaction.datetime)).scalar()
    return latest.date()


def get_last_n_occurrences(reference_date, day_of_week, n=4):
    """Find the last n dates (going backward) that fall on the given weekday, at or before reference_date."""
    days_back = (reference_date.weekday() - day_of_week) % 7
    most_recent = reference_date - timedelta(days=days_back)
    return [most_recent - timedelta(weeks=i) for i in range(n)][::-1]


def get_vendor_status(db, vendor_id, day_of_week, hour, reference_date):
    """Core calculation: compares the latest occurrence of this weekday/hour against a 4-week baseline."""
    dates = get_last_n_occurrences(reference_date, day_of_week, n=4)

    rows = db.query(
        func.date(models.Transaction.datetime).label("d"),
        models.Transaction.student_id,
    ).filter(
        models.Transaction.vendor_id == vendor_id,
        func.date(models.Transaction.datetime).in_(dates),
        func.extract("hour", models.Transaction.datetime) == hour,
    ).all()

    counts = {d: 0 for d in dates}
    students_by_date = {d: set() for d in dates}
    for row in rows:
        counts[row.d] += 1
        students_by_date[row.d].add(row.student_id)

    counts_list = [counts[d] for d in dates]
    baseline = sum(counts_list[:3]) / 3 if counts_list[:3] else 0
    current = counts_list[-1]
    current_students = len(students_by_date[dates[-1]])

    if is_suppressed(current_students):
        return {"status": "suppressed", "level": None, "student_count": current_students}

    if baseline == 0:
        level = "busy" if current > 0 else "normal"
    elif current <= baseline * QUIET_THRESHOLD:
        level = "quiet"
    elif current >= baseline * BUSY_THRESHOLD:
        level = "busy"
    else:
        level = "normal"

    recommendation = None
    if level == "quiet":
        recommendation = "Consider a promotion to lift traffic during this period."
    elif level == "busy":
        recommendation = "Avoid discounts - this period is already at or above normal capacity."

    return {
        "status": "ok",
        "level": level,
        "student_count": current_students,
        "recommendation": recommendation,
    }


def get_vendor_size_tiers(db, type_id):
    """Buckets vendors of a given type into small/medium/large by total transaction volume."""
    vendors = db.query(
        models.Transaction.vendor_id,
        func.count(models.Transaction.transaction_id).label("total"),
    ).join(models.Vendor).filter(
        models.Vendor.type_id == type_id
    ).group_by(models.Transaction.vendor_id).all()

    if not vendors:
        return {}

    sorted_vendors = sorted(vendors, key=lambda v: v.total)
    n = len(sorted_vendors)
    tiers = {}
    for i, v in enumerate(sorted_vendors):
        if i < n / 3:
            tiers[v.vendor_id] = "small"
        elif i < 2 * n / 3:
            tiers[v.vendor_id] = "medium"
        else:
            tiers[v.vendor_id] = "large"
    return tiers


def get_bulk_vendor_status(db, vendor_ids, day_of_week, hour, reference_date):
    """Same calculation as get_vendor_status, but for many vendors in ONE database query instead of one-per-vendor."""
    dates = get_last_n_occurrences(reference_date, day_of_week, n=4)

    rows = db.query(
        models.Transaction.vendor_id,
        func.date(models.Transaction.datetime).label("d"),
        models.Transaction.student_id,
    ).filter(
        models.Transaction.vendor_id.in_(vendor_ids),
        func.date(models.Transaction.datetime).in_(dates),
        func.extract("hour", models.Transaction.datetime) == hour,
    ).all()

    counts = {vid: {d: 0 for d in dates} for vid in vendor_ids}
    students_by_date = {vid: {d: set() for d in dates} for vid in vendor_ids}
    for row in rows:
        counts[row.vendor_id][row.d] += 1
        students_by_date[row.vendor_id][row.d].add(row.student_id)

    results = {}
    for vid in vendor_ids:
        counts_list = [counts[vid][d] for d in dates]
        baseline = sum(counts_list[:3]) / 3 if counts_list[:3] else 0
        current = counts_list[-1]
        current_students = len(students_by_date[vid][dates[-1]])

        if is_suppressed(current_students):
            results[vid] = {"status": "suppressed", "level": None, "student_count": current_students}
            continue

        if baseline == 0:
            level = "busy" if current > 0 else "normal"
        elif current <= baseline * QUIET_THRESHOLD:
            level = "quiet"
        elif current >= baseline * BUSY_THRESHOLD:
            level = "busy"
        else:
            level = "normal"

        recommendation = None
        if level == "quiet":
            recommendation = "Consider a promotion to lift traffic during this period."
        elif level == "busy":
            recommendation = "Avoid discounts - this period is already at or above normal capacity."

        results[vid] = {
            "status": "ok", "level": level,
            "student_count": current_students,
            "recommendation": recommendation,
        }
    return results