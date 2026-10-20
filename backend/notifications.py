from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import database
import models
from access.deps import get_current_user
import re

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)

@router.get("")
def get_notifications(
    vendor_id: int,
    include_cleared: bool = False,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
):
   
    if user.role != "Admin" and vendor_id not in user.vendor_ids:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this vendor",
        )

    query = db.query(models.Notification).filter(
        models.Notification.user_id == user.user_id,
        models.Notification.vendor_id == vendor_id,
    )

    if not include_cleared:
        query = query.filter(models.Notification.is_cleared.is_(False))

    notifications = (
        query.order_by(
            models.Notification.is_pinned.desc(),
            models.Notification.created_at.desc(),
        )
        .all()
    )

    result = []

    for item in notifications:
        contextual_events = []

        match = re.search(r"\[(\d{4}-\d{2}-\d{2})\]", item.message or "")

        stats_match = re.search(
            r"Actual transactions (increased|decreased) by ([\d.]+)% "
            r"\((\d+) transactions compared with a "
            r"four-week same-weekday average of ([\d.]+)\)",
            item.message or "",
        )

        if match:
            notification_date = datetime.strptime(
                match.group(1), "%Y-%m-%d"
            ).date()

            contextual_events = [
                {
                    "event_id": event.event_id,
                    "name": event.name,
                    "start_date": event.start_date.isoformat(),
                    "end_date": event.end_date.isoformat(),
                }
                for event in db.query(models.ContextualEvent)
                .filter(
                    models.ContextualEvent.start_date <= notification_date,
                    models.ContextualEvent.end_date >= notification_date,
                )
                .all()
            ]

        result.append({
            "notification_id": item.notification_id,
            "user_id": item.user_id,
            "vendor_id": item.vendor_id,
            "message": item.message,
            "trigger_type": item.trigger_type,
            "is_read": item.is_read,
            "is_pinned": item.is_pinned,
            "is_cleared": item.is_cleared,
            "created_at": item.created_at,
            "transaction_date": match.group(1) if match else None,
            "direction": stats_match.group(1) if stats_match else None,
            "percentage_change": float(stats_match.group(2)) if stats_match else None,
            "actual_count": int(stats_match.group(3)) if stats_match else None,
            "baseline_count": float(stats_match.group(4)) if stats_match else None,
            "contextual_events": contextual_events,
        })

    return result

@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
):
    item = db.query(models.Notification).filter(
        models.Notification.notification_id == notification_id,
        models.Notification.user_id == user.user_id,
    ).first()

    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    item.is_read = True
    db.commit()

    return {"message": "Notification marked as read"}


@router.patch("/{notification_id}/pin")
def toggle_notification_pin(
    notification_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
):
    item = db.query(models.Notification).filter(
        models.Notification.notification_id == notification_id,
        models.Notification.user_id == user.user_id,
    ).first()

    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    item.is_pinned = not item.is_pinned
    db.commit()

    return {
        "notification_id": item.notification_id,
        "is_pinned": item.is_pinned,
    }

@router.patch("/{notification_id}/clear")
def clear_notification(
    notification_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
):
    item = db.query(models.Notification).filter(
        models.Notification.notification_id == notification_id,
        models.Notification.user_id == user.user_id,
    ).first()

    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    item.is_cleared = True
    db.commit()

    return {"message": "Notification cleared"}


def check_transaction_change(db: Session, vendor_id: int, user_id: int):
    daily_rows = (
        db.query(
            func.date(models.Transaction.datetime).label("txn_date"),
            func.count(models.Transaction.transaction_id).label("transaction_count"),
        )
        .filter(models.Transaction.vendor_id == vendor_id)
        .group_by(func.date(models.Transaction.datetime))
        .order_by(func.date(models.Transaction.datetime))
        .all()
    )

    if not daily_rows:
        return

    daily_counts = {
        row.txn_date: row.transaction_count
        for row in daily_rows
    }

    latest_recorded_date = max(daily_counts)
    eligible_dates = [
        day for day in daily_counts
        if day < latest_recorded_date
    ]

    if not eligible_dates:
        return

    latest_date = max(eligible_dates)
    actual_count = daily_counts[latest_date]

    previous_dates = [
        latest_date - timedelta(days=7 * week)
        for week in range(1, 5)
    ]

    if not all(day in daily_counts for day in previous_dates):
        return

    baseline = sum(daily_counts[day] for day in previous_dates) / 4

    if baseline <= 0:
        return

    percentage_change = ((actual_count - baseline) / baseline) * 100

    if percentage_change >= 30:
        trigger_type = "transaction_increase"
        direction = "increased"
    elif percentage_change <= -30:
        trigger_type = "transaction_decrease"
        direction = "decreased"
    else:
        return

    message = (
        f"[{latest_date.isoformat()}] Actual transactions "
        f"{direction} by {abs(percentage_change):.1f}% "
        f"({actual_count} transactions compared with a "
        f"four-week same-weekday average of {baseline:.1f})."
    )

    existing_notification = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.vendor_id == vendor_id,
            models.Notification.trigger_type == trigger_type,
            models.Notification.message.contains(
                f"[{latest_date.isoformat()}]"
            ),
        )
        .first()
    )

    if existing_notification:
        return

    notification = models.Notification(
        user_id=user_id,
        vendor_id=vendor_id,
        message=message,
        trigger_type=trigger_type,
        is_read=False,
        is_pinned=False,
        is_cleared=False,
        created_at=datetime.now(timezone.utc),
    )

    db.add(notification)
    db.commit()
