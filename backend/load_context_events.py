import pandas as pd
from database import SessionLocal
import models

db = SessionLocal()

print("Loading context events...")
all_events = []
for year in [2023, 2024, 2025]:
    df = pd.read_csv(f"data/raw/context/context_events_{year}.csv")
    all_events.append(df)

events_df = pd.concat(all_events, ignore_index=True)

for _, row in events_df.iterrows():
    db.add(models.ContextEvent(
        context_id=row["context_id"],
        category=row["category"],
        subcategory=row.get("subcategory"),
        title=row["title"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        notes=row.get("notes"),
    ))

db.commit()
print(f"Loaded {len(events_df)} context events.")
db.close()