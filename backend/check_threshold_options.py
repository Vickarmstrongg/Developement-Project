from database import SessionLocal
from sqlalchemy import func
import models
from rush_hour import get_reference_date, get_last_n_occurrences

db = SessionLocal()
ref = get_reference_date(db)
dates = get_last_n_occurrences(ref, 4, n=4)  # Friday
hour = 12

print(f"Dates checked: {dates}")
print(f"Hour window: {hour-1} to {hour+1}\n")

for vendor_id in [21, 22, 23, 24, 25, 26, 27, 28, 29, 30]:
    students = db.query(func.count(func.distinct(models.Transaction.student_id))).filter(
        models.Transaction.vendor_id == vendor_id,
        func.date(models.Transaction.datetime).in_(dates),
        func.extract("hour", models.Transaction.datetime).in_([hour-1, hour, hour+1]),
    ).scalar()
    print(f"Vendor {vendor_id}: {students} distinct students (3-hour window, 4 weeks)")