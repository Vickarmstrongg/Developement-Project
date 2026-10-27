from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

import database
import models
from access.constants import Role
from access.deps import get_current_user

router = APIRouter(prefix="/api/reports", tags=["Reports"])

ALL_ROLES = {Role.ADMIN.value, Role.MANAGER.value, Role.STAFF.value}
ADMIN_MANAGER = {Role.ADMIN.value, Role.MANAGER.value}

# report_type -> (label shown on the Reports page, roles allowed to export it)
REPORT_TYPES = {
    "dashboard": ("Dashboard", ALL_ROLES),
    "rush_hour_radar": ("Rush Hour Radar", ALL_ROLES),
    "demand_forecast": ("Demand Forecast", ALL_ROLES),
    "fair_comparison": ("Fair Comparison", ADMIN_MANAGER),
    "calendar_events": ("Calendar / Context Events", {Role.ADMIN.value}),
}


class ExportIn(BaseModel):
    report_type: str
    vendor_id: Optional[int] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None


@router.post("/exports")
def log_export(
    body: ExportIn,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
) -> dict[str, Any]:
    if body.report_type not in REPORT_TYPES:
        raise HTTPException(status_code=422, detail="Unknown report type")
    if user.role not in REPORT_TYPES[body.report_type][1]:
        raise HTTPException(status_code=403, detail="You do not have access to this report")
    if (
        body.period_start and body.period_end
        and body.period_start > body.period_end
    ):
        raise HTTPException(status_code=422, detail="period_start must be on or before period_end")

    if body.vendor_id is not None:
        if user.role != Role.ADMIN.value and body.vendor_id not in user.vendor_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this vendor")
        if db.get(models.Vendor, body.vendor_id) is None:
            raise HTTPException(status_code=404, detail="Vendor not found")

    row = models.ReportExport(
        vendor_id=body.vendor_id,
        generated_by_user_id=user.user_id,
        report_type=body.report_type,
        period_start=body.period_start,
        period_end=body.period_end,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"report_id": row.report_id, "generated_at": row.generated_at.isoformat()}


@router.get("/exports")
def list_exports(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
) -> dict[str, Any]:
    query = db.query(models.ReportExport)

    if user.role == Role.MANAGER.value:
        query = query.filter(or_(
            models.ReportExport.vendor_id.in_(user.vendor_ids),
            models.ReportExport.generated_by_user_id == user.user_id,
        ))
    elif user.role != Role.ADMIN.value:  # Staff: only their own exports
        query = query.filter(models.ReportExport.generated_by_user_id == user.user_id)

    rows = (
        query.order_by(models.ReportExport.generated_at.desc())
        .limit(200)
        .all()
    )

    vendor_ids = {r.vendor_id for r in rows if r.vendor_id is not None}
    vendor_names = {}
    if vendor_ids:
        vendor_names = dict(
            db.query(models.Vendor.vendor_id, models.Vendor.name)
            .filter(models.Vendor.vendor_id.in_(vendor_ids))
            .all()
        )

    return {
        "exports": [
            {
                "report_id": r.report_id,
                "report_type": r.report_type,
                "report_label": REPORT_TYPES.get(r.report_type, (r.report_type,))[0],
                "vendor_id": r.vendor_id,
                "vendor_name": vendor_names.get(r.vendor_id),
                "period_start": r.period_start.isoformat() if r.period_start else None,
                "period_end": r.period_end.isoformat() if r.period_end else None,
                "generated_at": r.generated_at.isoformat(),
                "generated_by": (
                    (r.generated_by.full_name or r.generated_by.email)
                    if r.generated_by else "Unknown user"
                ),
                "generated_by_role": r.generated_by.role if r.generated_by else None,
            }
            for r in rows
        ]
    }