from database import Base, engine
import models

print("Dropping all tables...")
Base.metadata.drop_all(bind=engine)
print("Recreating empty tables...")
Base.metadata.create_all(bind=engine)
print("Done - all tables are now empty and ready for real data.")