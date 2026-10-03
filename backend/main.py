from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy import func
import database
import models
from rush_hour import get_bulk_vendor_status, get_vendor_size_tiers, get_reference_date, parse_gps

app = FastAPI(title="Byte & Bite API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "Byte & Bite API is running"}

@app.get("/db-check")
def db_check(db: Session = Depends(database.get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "connected"}

@app.get("/vendors")
def get_vendors(db: Session = Depends(database.get_db)):
    vendors = db.query(models.Vendor).all()
    return [
        {"vendor_id": v.vendor_id, "name": v.name, "address": v.address, "type_id": v.type_id}
        for v in vendors
    ]

@app.get("/vendors/{vendor_id}/summary")
def vendor_summary(vendor_id: int, db: Session = Depends(database.get_db)):
    vendor = db.query(models.Vendor).filter(models.Vendor.vendor_id == vendor_id).first()
    if not vendor:
        return {"error": "Vendor not found"}

    result = db.query(
        func.count(models.Transaction.transaction_id).label("total_transactions"),
        func.sum(models.Transaction.value).label("total_revenue"),
        func.avg(models.Transaction.value).label("avg_order_value"),
    ).filter(models.Transaction.vendor_id == vendor_id).first()

    return {
        "vendor_id": vendor.vendor_id,
        "vendor_name": vendor.name,
        "total_transactions": result.total_transactions,
        "total_revenue": float(result.total_revenue) if result.total_revenue else 0,
        "avg_order_value": round(float(result.avg_order_value), 2) if result.avg_order_value else 0,
    }

@app.get("/rush-hour-radar")
def rush_hour_radar(
    day: int, hour: int,
    type_id: int = None, size: str = None,
    db: Session = Depends(database.get_db)
):
    reference_date = get_reference_date(db)
    query = db.query(models.Vendor)
    if type_id:
        query = query.filter(models.Vendor.type_id == type_id)
    vendors = query.all()

    size_tiers = get_vendor_size_tiers(db, type_id) if type_id else {}
    vendor_ids = [v.vendor_id for v in vendors]
    status_by_vendor = get_bulk_vendor_status(db, vendor_ids, day, hour, reference_date)

    results = []
    for v in vendors:
        if size and size_tiers.get(v.vendor_id) != size:
            continue
        status = status_by_vendor[v.vendor_id]
        lat, lon = parse_gps(v.gps)
        results.append({
            "vendor_id": v.vendor_id, "name": v.name,
            "lat": lat, "lon": lon,
            **status,
        })

    return {"day": day, "hour": hour, "vendors": results}