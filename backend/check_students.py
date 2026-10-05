from database import SessionLocal
from sqlalchemy import func
import models
from rush_hour import get_reference_date, get_last_n_occurrences

db = SessionLocal()
ref = get_reference_date(db)
dates = get_last_n_occurrences(ref, 4, n=4)  # Friday = 4
print("Dates checked:", dates)

for d in dates:
    students = db.query(func.count(func.distinct(models.Transaction.student_id))).filter(
        models.Transaction.vendor_id == 21,
        func.date(models.Transaction.datetime) == d,
    ).scalar()
    print(f"{d}: {students} distinct students (whole day)")

total = db.query(func.count(func.distinct(models.Transaction.student_id))).filter(
    models.Transaction.vendor_id == 21,
    func.date(models.Transaction.datetime).in_(dates),
).scalar()
print("Total distinct students across all 4 dates combined:", total)