from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import database

app = FastAPI(title="Byte & Bite API")

@app.get("/")
def health_check():
    return {"status": "Byte & Bite API is running"}

@app.get("/db-check")
def db_check(db: Session = Depends(database.get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "connected"}