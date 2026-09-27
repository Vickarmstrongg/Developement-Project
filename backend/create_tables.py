from database import Base, engine
import models

print("Connecting to:", engine.url)
Base.metadata.create_all(bind=engine)
print("Tables created successfully.")
print("Tables now in metadata:", list(Base.metadata.tables.keys()))