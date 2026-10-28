"""
Fair Comparison Score Engine — Byte & Bite
------------------------------------------
Purpose:
    Allows a vendor to benchmark their performance against an aggregated,
    anonymised cohort of similar participating businesses (same vendor type
    and size tier).

Rules (BRD v2 & Client Minutes):
    - Peers grouped by vendor type (type_id) + size (small, medium, large)[cite: 3].
    - Minimum 3 peer businesses in the cohort (FR-19, NFR-02)[cite: 3].
    - Zero competitor names or individual sales numbers exposed[cite: 3].
    - Output label: "above_average", "average", or "below_average"[cite: 3].
    - Optional filter by specific date[cite: 3].
"""

from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import models
from performance import timed_stage

MIN_PEER_BUSINESSES = 3
AVERAGE_BAND_PERCENTAGE = 0.10  # Within ±10% of peer mean is "average"


def _operational_tier(txn_count: int) -> str:
    if txn_count < 1500:
        return "small"
    if txn_count < 3000:
        return "medium"
    return "large"


def get_vendor_operational_tier(db: Session, vendor_id: int) -> str:
    """
    Derives vendor operational size dynamically from total transaction volume.
    Matches the tiering logic established in the project.
    """
    txn_count = (
        db.query(func.count(models.Transaction.transaction_id))
        .filter(models.Transaction.vendor_id == vendor_id)
        .scalar() or 0
    )
    return _operational_tier(txn_count)


@timed_stage("fair_comparison.calculation")
def calculate_fair_comparison(
    db: Session,
    vendor_id: int,
    filter_date: Optional[date] = None
) -> dict:
    # 1. Fetch vendor to verify it exists
    vendor = db.query(models.Vendor).filter(models.Vendor.vendor_id == vendor_id).first()
    if not vendor:
        return {"error": "Vendor not found"}

    # Fetch vendor type name
    vendor_type = db.query(models.VendorType).filter(models.VendorType.type_id == vendor.type_id).first()
    type_name = vendor_type.name if vendor_type else "Food & Beverage"

    # Fetch same-type vendors and transaction totals together to avoid one
    # full-history count query per vendor.
    same_type_vendors = (
        db.query(models.Vendor)
        .filter(models.Vendor.type_id == vendor.type_id)
        .all()
    )
    same_type_vendor_ids = [v.vendor_id for v in same_type_vendors]
    transaction_counts = dict(
        db.query(
            models.Transaction.vendor_id,
            func.count(models.Transaction.transaction_id).label("total"),
        )
        .filter(models.Transaction.vendor_id.in_(same_type_vendor_ids))
        .group_by(models.Transaction.vendor_id)
        .all()
    ) if same_type_vendor_ids else {}
    vendor_size = _operational_tier(transaction_counts.get(vendor.vendor_id, 0))

    # 2. Determine date window (single day if requested, or latest 7 days recorded)
    if filter_date:
        start_date = filter_date
        end_date = filter_date
    else:
        # Default: latest 7 days of 2025 transaction data
        latest_txn = db.query(func.max(func.date(models.Transaction.datetime))).scalar()
        if not latest_txn:
            return {"error": "No transaction data available"}
        end_date = latest_txn
        start_date = end_date - timedelta(days=6)

    # Filter peers by matching operational size tier.
    peer_vendor_ids = [
        v.vendor_id for v in same_type_vendors
        if _operational_tier(transaction_counts.get(v.vendor_id, 0)) == vendor_size
    ]

    # Privacy constraint check: Minimum 3 peer businesses in cohort
    if len(peer_vendor_ids) < MIN_PEER_BUSINESSES:
        return {
            "status": "suppressed",
            "reason": f"Fewer than {MIN_PEER_BUSINESSES} peer businesses in this cohort.",
            "peer_group_size": len(peer_vendor_ids),
            "vendor_size": vendor_size,
            "vendor_type": type_name
        }

    # 4. Query aggregated metrics for all peers in the cohort
    cohort_stats = (
        db.query(
            models.Transaction.vendor_id,
            func.count(models.Transaction.transaction_id).label("txn_count"),
            func.sum(models.Transaction.value).label("total_revenue"),
        )
        .filter(
            models.Transaction.vendor_id.in_(peer_vendor_ids),
            func.date(models.Transaction.datetime) >= start_date,
            func.date(models.Transaction.datetime) <= end_date
        )
        .group_by(models.Transaction.vendor_id)
        .all()
    )

    total_cohort_businesses = len(cohort_stats)
    if total_cohort_businesses < MIN_PEER_BUSINESSES:
        return {
            "status": "suppressed",
            "reason": f"Only {total_cohort_businesses} businesses had transactions in this window (minimum {MIN_PEER_BUSINESSES} required).",
            "peer_group_size": total_cohort_businesses
        }

    # 5. Extract target vendor's metrics & compute cohort averages
    target_stats = next((s for s in cohort_stats if s.vendor_id == vendor_id), None)
    vendor_txns = target_stats.txn_count if target_stats else 0
    vendor_revenue = float(target_stats.total_revenue or 0.0) if target_stats else 0.0

    peer_avg_txns = round(sum(s.txn_count for s in cohort_stats) / total_cohort_businesses, 1)
    peer_avg_revenue = round(sum(float(s.total_revenue or 0.0) for s in cohort_stats) / total_cohort_businesses, 2)

    # Fair Comparison (if don't like then delete this code below here and above 6. This is for the daily transaction counts for venue and peer group

    daily_stats = (
        db.query(
            func.date(models.Transaction.datetime).label("transaction_date"),
            models.Transaction.vendor_id,
            func.count(models.Transaction.transaction_id).label("txn_count")
        )
        .filter(
            models.Transaction.vendor_id.in_(peer_vendor_ids),
            func.date(models.Transaction.datetime) >= start_date,
            func.date(models.Transaction.datetime) <= end_date
        )
        .group_by(
            func.date(models.Transaction.datetime),
            models.Transaction.vendor_id
        )
        .all()
    )

    daily_counts = {}

    for row in daily_stats:
        day = str(row.transaction_date)
        daily_counts[(day, row.vendor_id)] = row.txn_count

    daily_trend = []
    current_date = start_date

    while current_date <= end_date:
        day = current_date.isoformat()

        venue_count = daily_counts.get((day, vendor_id), 0)

        peer_total = sum(
            daily_counts.get((day, peer_id), 0)
            for peer_id in peer_vendor_ids
        )

        daily_peer_average = round(
            peer_total / total_cohort_businesses,
            1
        )

        daily_trend.append({
            "date": day,
            "vendor_transactions": venue_count,
            "peer_average_transactions": daily_peer_average
        })

        current_date += timedelta(days=1)


    # -------------------------Ends here------------------------------

    # 6. Determine classification label (above_average / average / below_average)
    if peer_avg_txns > 0:
        ratio = vendor_txns / peer_avg_txns
        if ratio > (1 + AVERAGE_BAND_PERCENTAGE):
            comparison_result = "above_average"
        elif ratio < (1 - AVERAGE_BAND_PERCENTAGE):
            comparison_result = "below_average"
        else:
            comparison_result = "average"
    else:
        comparison_result = "average"

    cohort_label = f"{vendor_size.capitalize()} {type_name.lower()}s ({total_cohort_businesses} participating businesses)"

    return {
        "status": "ok",
        "vendor_id": vendor.vendor_id,
        "vendor_name": vendor.name,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "peer_group": {
            "description": cohort_label,
            "vendor_type": type_name,
            "size_tier": vendor_size,
            "participating_businesses": total_cohort_businesses
        },
        "metrics": {
            "vendor_transactions": vendor_txns,
            "peer_average_transactions": peer_avg_txns,
            "vendor_revenue": round(vendor_revenue, 2),
            "peer_average_revenue": peer_avg_revenue,
            "comparison_result": comparison_result
        },
        # Delete this if don't like (this is for the trend line graph)
        "daily_trend": daily_trend
    }