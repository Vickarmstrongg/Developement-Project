from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_transactions_vendor_datetime "
        "ON transactions (vendor_id, datetime)"
    ))
    conn.commit()
print("Index created.")