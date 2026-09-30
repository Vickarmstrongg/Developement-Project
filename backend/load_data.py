import pandas as pd
from database import SessionLocal
import models

db = SessionLocal()

print("Loading vendor types...")
vendor_types_df = pd.read_csv("data/raw/Vendor_Type.csv")
for _, row in vendor_types_df.iterrows():
    db.add(models.VendorType(type_id=row["type_id"], name=row["name"]))
db.commit()
print(f"Loaded {len(vendor_types_df)} vendor types.")

print("Loading vendors...")
vendors_df = pd.read_csv("data/raw/Vendor.csv")
for _, row in vendors_df.iterrows():
    db.add(models.Vendor(
        vendor_id=row["vendor_id"], name=row["name"],
        address=row["address"], gps=row["gps"], type_id=row["type_id"]
    ))
db.commit()
print(f"Loaded {len(vendors_df)} vendors.")

print("Loading students...")
students_df = pd.read_csv("data/raw/Student.csv")
for _, row in students_df.iterrows():
    db.add(models.Student(
        id_number=row["id_number"], last_name=row["last_name"],
        first_name=row["first_name"], dob=row["dob"], gender=row["gender"],
        email=row["email"], phone=row["phone"], address=row["address"]
    ))
db.commit()
print(f"Loaded {len(students_df)} students.")

print("Loading transactions (filtered to 2025, relevant vendor types)...")

relevant_vendor_ids = set(
    vendors_df[vendors_df["type_id"].isin([3, 4, 5])]["vendor_id"]
)

total_loaded = 0
chunk_size = 50000

for chunk in pd.read_csv("data/raw/Transaction.csv", chunksize=chunk_size):
    chunk["datetime"] = pd.to_datetime(chunk["datetime"])
    chunk = chunk[chunk["datetime"].dt.year == 2025]
    chunk = chunk[chunk["vendor_id"].isin(relevant_vendor_ids)]

    if len(chunk) == 0:
        continue

    records = [
        models.Transaction(
            transaction_id=row["transaction_id"], student_id=row["student_id"],
            vendor_id=row["vendor_id"], datetime=row["datetime"],
            value=row["value"], discount=row["discount"]
        )
        for _, row in chunk.iterrows()
    ]
    db.bulk_save_objects(records)
    db.commit()
    total_loaded += len(records)
    print(f"  ...loaded {total_loaded} transactions so far")

print(f"Done. Total transactions loaded: {total_loaded}")
db.close()