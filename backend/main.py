from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import date
from typing import Optional

from access import routes as auth_routes, users as user_routes
from access.settings import CORS_ORIGINS
from access.deps import get_current_user, require_vendor_access, shape_for_role

import database
import models
import context_events
from fair_comparison import calculate_fair_comparison

from access import routes as auth_routes, users as user_routes
from access.settings import CORS_ORIGINS
from access.deps import get_current_user, require_vendor_access, require_roles, shape_for_role
from access.constants import Role

from rush_hour import (
    get_bulk_vendor_status,
    get_vendor_size_tiers,
    get_reference_date,
    parse_gps,
    get_vendor_status,
    get_weekly_pattern,
)
from demand_forecast import calculate_demand_forecast


app = FastAPI(title="Byte & Bite API")

app.include_router(context_events.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)   # /auth/...
app.include_router(user_routes.router)   # /users/... (Admin only)


@app.get("/vendors/{vendor_id}/weekly-pattern")
def weekly_pattern(
    vendor_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(require_vendor_access)

):
    reference_date = get_reference_date(db)
    pattern = get_weekly_pattern(db, vendor_id, reference_date)
    return shape_for_role(user, {"vendor_id": vendor_id, "pattern": pattern})

@app.get("/")
def health_check():
    return {"status": "Byte & Bite API is running"}


@app.get("/db-check")
def db_check(db: Session = Depends(database.get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "connected"}


@app.get("/vendors")
def get_vendors(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user),
):
    query = db.query(models.Vendor)
    if not user.all_vendors:  # Manager / Staff only see their linked vendors
        if not user.vendor_ids:
            return []
        query = query.filter(models.Vendor.vendor_id.in_(user.vendor_ids))
    vendors = query.all()
    return [
        {"vendor_id": v.vendor_id, "name": v.name, "address": v.address, "type_id": v.type_id}
        for v in vendors
    ]


@app.get("/vendors/{vendor_id}/summary")
def vendor_summary(
    vendor_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(require_vendor_access)
):
    vendor = (
        db.query(models.Vendor)
        .filter(models.Vendor.vendor_id == vendor_id)
        .first()
    )

    if not vendor:
        return {"error": "Vendor not found"}

    result = db.query(
        func.count(
            models.Transaction.transaction_id
        ).label("total_transactions"),
        func.sum(
            models.Transaction.value
        ).label("total_revenue"),
        func.avg(
            models.Transaction.value
        ).label("avg_order_value"),
    ).filter(
        models.Transaction.vendor_id == vendor_id
    ).first()

    return shape_for_role(user,{
        "vendor_id": vendor.vendor_id,
        "vendor_name": vendor.name,
        "total_transactions": result.total_transactions,
        "total_revenue": (
            float(result.total_revenue)
            if result.total_revenue else 0
        ),
        "avg_order_value": (
            round(float(result.avg_order_value), 2)
            if result.avg_order_value else 0
        ),
    })


@app.get("/vendors/{vendor_id}/demand-forecast")
def get_demand_forecast(
    vendor_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(require_vendor_access)
):
    result = calculate_demand_forecast(db, vendor_id)
    return shape_for_role(user, result)


@app.get("/vendors/{vendor_id}/fair-comparison",
        dependencies=[Depends(require_roles(Role.ADMIN, Role.MANAGER)), Depends(require_vendor_access)])
def get_fair_comparison(
    vendor_id: int,
    filter_date: Optional[date] = None,
    db: Session = Depends(database.get_db)
):
    return calculate_fair_comparison(
        db=db,
        vendor_id=vendor_id,
        filter_date=filter_date
    )


@app.get("/rush-hour-radar", dependencies=[Depends(get_current_user)])
def rush_hour_radar(
    day: int,
    hour: int,
    type_id: int = None,
    size: str = None,
    db: Session = Depends(database.get_db)
):
    reference_date = get_reference_date(db)

    query = db.query(models.Vendor)

    if type_id:
        query = query.filter(models.Vendor.type_id == type_id)

    vendors = query.all()

    size_tiers = (
        get_vendor_size_tiers(db, type_id)
        if type_id else {}
    )

    vendor_ids = [v.vendor_id for v in vendors]

    status_by_vendor = get_bulk_vendor_status(
        db, vendor_ids, day, hour, reference_date
    )

    results = []

    for v in vendors:
        if size and size_tiers.get(v.vendor_id) != size:
            continue

        status = status_by_vendor[v.vendor_id]
        lat, lon = parse_gps(v.gps)

        results.append({
            "vendor_id": v.vendor_id,
            "name": v.name,
            "lat": lat,
            "lon": lon,
            **status,
        })

    return {
        "day": day,
        "hour": hour,
        "vendors": results
    }
