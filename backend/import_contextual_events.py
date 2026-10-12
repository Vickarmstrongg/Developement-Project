import argparse
import csv
import json
from datetime import date, datetime, time, timezone
from pathlib import Path

import models
from database import SessionLocal


DATA_DIRECTORY = (
    Path(__file__).resolve().parent / "data" / "raw" / "context"
)
SOURCE_LABEL = "Byte & Bite context dataset"
YEARS = (2023, 2024, 2025)
OPTIONAL_TEXT_FIELDS = (
    "subcategory",
    "location",
    "campus",
    "faculty",
    "scope",
    "source_organisation",
    "source_name",
    "source_file",
    "source_url",
    "source_page",
    "verification_status",
    "notes",
)
REQUIRED_COLUMNS = {
    "context_id",
    "year",
    "category",
    "title",
    "start_date",
    "end_date",
}


def optional_text(row, field):
    value = row.get(field)
    if value is None:
        return None
    return value.strip() or None


def parse_date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from exc


def parse_time(row, field):
    value = optional_text(row, field)
    if value is None:
        return None
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid time") from exc
    if parsed.tzinfo is not None:
        raise ValueError(f"{field} must not include a timezone")
    return parsed


def parse_bool(row, field):
    value = optional_text(row, field)
    if value is None:
        return None
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{field} must be true, false, or blank")


def map_row(row, expected_year):
    context_id = optional_text(row, "context_id")
    category = optional_text(row, "category")
    name = optional_text(row, "title")
    if not context_id:
        raise ValueError("context_id is required")
    if not category:
        raise ValueError("category is required")
    if not name:
        raise ValueError("title is required")

    try:
        source_year = int(row.get("year", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("year must be an integer") from exc
    if source_year != expected_year:
        raise ValueError(
            f"year {source_year} does not match source file year "
            f"{expected_year}"
        )

    values = {
        "source_context_id": context_id,
        "source_year": source_year,
        "name": name,
        "event_type": category,
        "start_date": parse_date(row.get("start_date"), "start_date"),
        "start_time": parse_time(row, "start_time"),
        "end_date": parse_date(row.get("end_date"), "end_date"),
        "end_time": parse_time(row, "end_time"),
        "all_day": parse_bool(row, "all_day"),
        "source": SOURCE_LABEL,
    }
    if values["end_date"] < values["start_date"]:
        raise ValueError("end_date cannot be before start_date")

    values.update({
        field: optional_text(row, field)
        for field in OPTIONAL_TEXT_FIELDS
    })
    return values


def load_source_rows(years, rejected):
    rows = []
    seen_ids = set()
    for year in years:
        path = DATA_DIRECTORY / f"context_events_{year}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Context source file not found: {path}")

        with path.open(encoding="utf-8-sig", newline="") as source_file:
            reader = csv.DictReader(source_file)
            missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames or ())
            if missing_columns:
                raise ValueError(
                    f"{path.name} is missing columns: "
                    f"{', '.join(sorted(missing_columns))}"
                )
            for line_number, row in enumerate(reader, start=2):
                try:
                    values = map_row(row, year)
                    context_id = values["source_context_id"]
                    if context_id in seen_ids:
                        raise ValueError(
                            f"duplicate context_id {context_id} in source files"
                        )
                    seen_ids.add(context_id)
                    rows.append((values, path.name, line_number))
                except ValueError as exc:
                    rejected.append({
                        "file": path.name,
                        "line": line_number,
                        "context_id": optional_text(row, "context_id"),
                        "reason": str(exc),
                    })
    return rows


def count_rows(db, model):
    return db.query(model).count()


def import_rows(db, rows):
    counts = {"imported": 0, "updated": 0, "skipped": 0}
    for values, _filename, _line_number in rows:
        existing = (
            db.query(models.ContextualEvent)
            .filter(
                models.ContextualEvent.source_context_id
                == values["source_context_id"]
            )
            .one_or_none()
        )
        if existing is None:
            db.add(models.ContextualEvent(
                **values,
                updated_at=datetime.now(timezone.utc),
            ))
            counts["imported"] += 1
            continue

        changed = any(
            getattr(existing, field) != value
            for field, value in values.items()
        )
        if not changed:
            counts["skipped"] += 1
            continue

        for field, value in values.items():
            setattr(existing, field, value)
        existing.updated_at = datetime.now(timezone.utc)
        counts["updated"] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Import Byte & Bite calendar CSVs into contextual_events. "
            "Reruns update changed source records without deleting data."
        )
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        choices=YEARS,
        default=YEARS,
        help="Source years to import (default: all available years).",
    )
    args = parser.parse_args()
    rejected = []
    rows = load_source_rows(args.years, rejected)

    with SessionLocal() as db:
        legacy_before = count_rows(db, models.ContextEvent)
        target_before = count_rows(db, models.ContextualEvent)
        results = import_rows(db, rows)
        db.commit()
        legacy_after = count_rows(db, models.ContextEvent)
        target_after = count_rows(db, models.ContextualEvent)

    summary = {
        "source_records": len(rows) + len(rejected),
        **results,
        "rejected": len(rejected),
        "contextual_events_before": target_before,
        "contextual_events_after": target_after,
        "context_events_before": legacy_before,
        "context_events_after": legacy_after,
    }
    print(json.dumps(summary, indent=2))
    if rejected:
        print("Rejected records:")
        print(json.dumps(rejected, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
