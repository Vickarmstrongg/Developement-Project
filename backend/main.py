from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import database
import models

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