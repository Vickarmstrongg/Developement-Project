from database import SessionLocal
import models

db = SessionLocal()

# Step 1
db.add_all([
    models.VendorType(type_id=1, name="Restaurant (Student Delivery)"),
    models.VendorType(type_id=2, name="Takeaway / Fast Food"),
])
db.commit()
print("Vendor types added.")

# Step 2
db.add_all([
    models.Vendor(vendor_id=1, name="Eikestad Eats", address="82 Bird Street, Stellenbosch", gps="-33.94900,18.85100", type_id=1),
    models.Vendor(vendor_id=2, name="Dorp Street Diner", address="29 Plein Street, Stellenbosch", gps="-33.92054,18.86707", type_id=1),
    models.Vendor(vendor_id=3, name="Quick Bites Stellenbosch", address="14 Church Street, Stellenbosch", gps="-33.93500,18.86000", type_id=2),
])
db.commit()
print("Vendors added.")

db.close()
print("Seed data added.")