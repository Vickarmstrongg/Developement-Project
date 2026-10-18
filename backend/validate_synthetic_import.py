"""Read-only aggregate validation for the reviewed Byte & Bite data rebuild.

Requires BYTEBITE_TARGET_BRANCH=synthetic-data-dev,
BYTEBITE_DEV_DB_HOST, and BYTEBITE_DEV_DB_NAME. This script does not select
student or transaction records and marks unavailable checks as failures rather
than treating them as passes.
"""

import csv
import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import database


EXPECTED_BRANCH = "synthetic-data-dev"
SOURCE_LABEL = "Byte & Bite context dataset"
BACKEND = Path(__file__).resolve().parent
DATA_DIRECTORY = BACKEND / "data" / "raw" / "Byte_&_Bite Data Pack"
CONTEXT_DIRECTORY = BACKEND / "data" / "raw" / "context"
SOURCE_COUNTS = {
    "students": 12_000,
    "vendor_types": 7,
    "vendors": 160,
    "transactions": 4_075_965,
}
CONTEXT_FILES = (
    CONTEXT_DIRECTORY / "context_events_2023.csv",
    CONTEXT_DIRECTORY / "context_events_2024.csv",
    CONTEXT_DIRECTORY / "context_events_2025.csv",
)
CONTEXT_COUNTS = {2023: 67, 2024: 59, 2025: 65}
ORIGINAL_COLUMNS = {
    "students": {
        "id_number", "last_name", "first_name", "dob", "gender",
        "email", "phone", "address",
    },
    "vendor_types": {"type_id", "name"},
    "vendors": {"vendor_id", "name", "address", "gps", "type_id"},
    "transactions": {
        "transaction_id", "student_id", "vendor_id", "datetime", "value", "discount",
    },
    "context_events": {
        "context_id", "category", "subcategory", "title",
        "start_date", "end_date", "notes",
    },
}
SUPPORTING_COLUMNS = {
    "users": {
        "user_id", "email", "password_hash", "role", "vendor_id", "full_name",
        "status", "token_hash", "token_expires_at", "failed_login_attempts", "locked",
    },
    "user_vendor_links": {"user_id", "vendor_id"},
    "notifications": {
        "notification_id", "user_id", "vendor_id", "message", "trigger_type",
        "is_read", "is_pinned", "is_cleared", "created_at",
    },
    "report_exports": {
        "report_id", "vendor_id", "generated_by_user_id", "report_type",
        "period_start", "period_end", "generated_at",
    },
    "contextual_events": {
        "event_id", "source_context_id", "source_year", "name", "event_type",
        "subcategory", "start_date", "start_time", "end_date", "end_time",
        "all_day", "location", "campus", "faculty", "scope", "source",
        "source_organisation", "source_name", "source_file", "source_url",
        "source_page", "verification_status", "notes", "created_by_user_id",
        "updated_at",
    },
}


def require_target() -> None:
    if os.getenv("BYTEBITE_TARGET_BRANCH") != EXPECTED_BRANCH:
        raise RuntimeError("BYTEBITE_TARGET_BRANCH must be synthetic-data-dev.")
    expected_host = os.getenv("BYTEBITE_DEV_DB_HOST")
    expected_database = os.getenv("BYTEBITE_DEV_DB_NAME")
    if not expected_host or not expected_database:
        raise RuntimeError("Set BYTEBITE_DEV_DB_HOST and BYTEBITE_DEV_DB_NAME.")
    if database.engine.url.host != expected_host:
        raise RuntimeError("DATABASE_URL host does not match the expected development host.")
    if database.engine.url.database != expected_database:
        raise RuntimeError("DATABASE_URL database does not match the expected development database.")


def source_event_rows() -> dict[str, dict]:
    events = {}
    for path in CONTEXT_FILES:
        if not path.is_file():
            raise FileNotFoundError(f"Missing context source file: {path.name}")
        expected_year = int(path.stem[-4:])
        records_before_file = len(events)
        with path.open("r", encoding="utf-8-sig", newline="") as source_file:
            reader = csv.DictReader(source_file)
            required = {
                "context_id", "year", "category", "title", "start_date",
                "start_time", "end_date", "end_time", "all_day",
            }
            if not required.issubset(set(reader.fieldnames or ())):
                raise ValueError(f"{path.name} is missing required event headers.")
            for row in reader:
                source_id = (row.get("context_id") or "").strip()
                if not source_id or source_id in events:
                    raise ValueError(f"{path.name} has a blank or duplicate event key.")
                if int(row["year"]) != expected_year:
                    raise ValueError(f"{path.name} contains a year/file mismatch.")
                title = (row.get("title") or "").strip()
                category = (row.get("category") or "").strip()
                if not title or not category:
                    raise ValueError(f"{path.name} has a blank required event field.")

                def parse_optional_time(value):
                    parsed = time.fromisoformat(value) if (value or "").strip() else None
                    if parsed is not None and parsed.tzinfo is not None:
                        raise ValueError(f"{path.name} has a timezone-aware event time.")
                    return parsed

                bool_text = (row.get("all_day") or "").strip().casefold()
                if bool_text and bool_text not in {"true", "false"}:
                    raise ValueError(f"{path.name} contains an invalid all_day value.")
                start_date = date.fromisoformat(row["start_date"])
                end_date = date.fromisoformat(row["end_date"])
                if end_date < start_date:
                    raise ValueError(f"{path.name} has an event date range in reverse.")
                events[source_id] = {
                    "source_year": expected_year,
                    "name": title,
                    "event_type": category,
                    "start_date": start_date,
                    "start_time": parse_optional_time(row.get("start_time")),
                    "end_date": end_date,
                    "end_time": parse_optional_time(row.get("end_time")),
                    "all_day": (
                        None if not bool_text else bool_text == "true"
                    ),
                }
        if len(events) - records_before_file != CONTEXT_COUNTS[expected_year]:
            raise ValueError(f"{path.name} does not contain its reviewed record count.")
    if len(events) != 191:
        raise ValueError("Context source files do not contain the 191 reviewed event records.")
    return events


def main() -> int:
    require_target()
    expected_events = source_event_rows()
    checks = []

    def add_check(name: str, passed: bool, observed, expected, explanation: str):
        checks.append({
            "check": name,
            "status": "PASS" if passed else "FAIL",
            "observed": observed,
            "expected": expected,
            "explanation": explanation,
        })

    with database.engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '120s'")
            identity = connection.execute(text("""
                SELECT current_database() AS database_name,
                       current_schema() AS schema_name
            """)).mappings().one()
            if identity["database_name"] != os.environ["BYTEBITE_DEV_DB_NAME"]:
                raise RuntimeError("Connected database does not match the expected development database.")
            if identity["schema_name"] != "public":
                raise RuntimeError("Connected session is not using the public schema.")

            tables = set(connection.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
            """)).scalars())
            all_expected_columns = {**ORIGINAL_COLUMNS, **SUPPORTING_COLUMNS}
            for table_name, expected_columns in all_expected_columns.items():
                if table_name not in tables:
                    add_check(
                        f"table {table_name} exists", False, "missing", "present",
                        "A required project table is absent.",
                    )
                    continue
                actual_columns = set(connection.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema() AND table_name = :table_name
                """), {"table_name": table_name}).scalars())
                missing = expected_columns - actual_columns
                extra = actual_columns - expected_columns
                add_check(
                    f"columns in {table_name}", not missing and not extra,
                    {
                        "column_count": len(actual_columns),
                        "missing_count": len(missing),
                        "extra_count": len(extra),
                    },
                    {"exact_column_count": len(expected_columns)},
                    "Column set matches the reviewed schema."
                    if not missing and not extra
                    else "Column set differs from the reviewed schema.",
                )

            for table_name, expected_count in SOURCE_COUNTS.items():
                if table_name in tables:
                    observed = connection.execute(
                        text(f"SELECT COUNT(*) FROM public.{table_name}")
                    ).scalar_one()
                    add_check(
                        f"row count {table_name}", observed == expected_count,
                        observed, expected_count,
                        "Exact aggregate count compared with the inspected CSV.",
                    )

            if {"students", "transactions", "vendors", "vendor_types"} <= tables:
                transaction_stats = connection.execute(text("""
                    SELECT MIN(datetime) AS first_transaction,
                           MAX(datetime) AS last_transaction,
                           MIN(value) AS minimum_value,
                           MAX(value) AS maximum_value,
                           MIN(discount) AS minimum_discount,
                           MAX(discount) AS maximum_discount,
                           COUNT(*) FILTER (WHERE value < 0 OR discount < 0)
                               AS negative_amount_rows,
                           COUNT(*) FILTER (
                               WHERE student_id IS NOT NULL
                                 AND student_id !~ '^dev_[0-9a-f]{64}$'
                           ) AS non_pseudonymous_transaction_links
                    FROM public.transactions
                """)).mappings().one()
                add_check(
                    "transaction date and numeric ranges",
                    (
                        transaction_stats["first_transaction"]
                        == datetime(2024, 1, 1, 7, 29, 8)
                        and transaction_stats["last_transaction"]
                        == datetime(2026, 10, 9, 4, 20, 52)
                        and transaction_stats["minimum_value"] == Decimal("5.00")
                        and transaction_stats["maximum_value"] == Decimal("2757.69")
                        and transaction_stats["minimum_discount"] == Decimal("0.00")
                        and transaction_stats["maximum_discount"] == Decimal("168.19")
                        and transaction_stats["negative_amount_rows"] == 0
                        and transaction_stats["non_pseudonymous_transaction_links"] == 0
                    ),
                    {
                        key: transaction_stats[key]
                        for key in transaction_stats.keys()
                    },
                    {
                        "first_transaction": datetime(2024, 1, 1, 7, 29, 8),
                        "last_transaction": datetime(2026, 10, 9, 4, 20, 52),
                        "minimum_value": Decimal("5.00"),
                        "maximum_value": Decimal("2757.69"),
                        "minimum_discount": Decimal("0.00"),
                        "maximum_discount": Decimal("168.19"),
                        "negative_amount_rows": 0,
                        "non_pseudonymous_transaction_links": 0,
                    },
                    "Only aggregate minima, maxima, and counts were queried.",
                )
                invalid_transaction_links = connection.execute(text("""
                    SELECT COUNT(*)
                    FROM public.transactions AS transaction_row
                    LEFT JOIN public.students AS student
                      ON student.id_number = transaction_row.student_id
                    WHERE student.id_number IS NULL
                       OR transaction_row.student_id IS NULL
                """)).scalar_one()
                invalid_vendor_links = connection.execute(text("""
                    SELECT COUNT(*)
                    FROM public.transactions AS transaction_row
                    LEFT JOIN public.vendors AS vendor
                      ON vendor.vendor_id = transaction_row.vendor_id
                    WHERE vendor.vendor_id IS NULL
                       OR transaction_row.vendor_id IS NULL
                """)).scalar_one()
                invalid_type_links = connection.execute(text("""
                    SELECT COUNT(*)
                    FROM public.vendors AS vendor
                    LEFT JOIN public.vendor_types AS vendor_type
                      ON vendor_type.type_id = vendor.type_id
                    WHERE vendor_type.type_id IS NULL OR vendor.type_id IS NULL
                """)).scalar_one()
                add_check(
                    "foreign-key target rows",
                    invalid_transaction_links == 0
                    and invalid_vendor_links == 0
                    and invalid_type_links == 0,
                    {
                        "transaction_to_student": invalid_transaction_links,
                        "transaction_to_vendor": invalid_vendor_links,
                        "vendor_to_type": invalid_type_links,
                    },
                    {
                        "transaction_to_student": 0,
                        "transaction_to_vendor": 0,
                        "vendor_to_type": 0,
                    },
                    "Aggregate anti-joins confirm all source relationships resolve.",
                )

            if "context_events" in tables:
                legacy_count = connection.execute(
                    text("SELECT COUNT(*) FROM public.context_events")
                ).scalar_one()
                add_check(
                    "legacy context_events preserved",
                    legacy_count == 191, legacy_count, 191,
                    "The legacy table remains separate and retains its 191 inspected records.",
                )

            expected_constraint_fragments = {
                "students": ("PRIMARY KEY (id_number)",),
                "vendors": (
                    "PRIMARY KEY (vendor_id)",
                    "FOREIGN KEY (type_id) REFERENCES vendor_types(type_id)",
                ),
                "vendor_types": ("PRIMARY KEY (type_id)",),
                "transactions": (
                    "PRIMARY KEY (transaction_id)",
                    "FOREIGN KEY (student_id) REFERENCES students(id_number)",
                    "FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id)",
                ),
                "users": (
                    "PRIMARY KEY (user_id)",
                    "UNIQUE (email)",
                ),
                "context_events": ("PRIMARY KEY (context_id)",),
                "user_vendor_links": (
                    "PRIMARY KEY (user_id, vendor_id)",
                    "FOREIGN KEY (user_id) REFERENCES users(user_id)",
                ),
                "notifications": (
                    "PRIMARY KEY (notification_id)",
                    "FOREIGN KEY (user_id) REFERENCES users(user_id)",
                ),
                "report_exports": (
                    "PRIMARY KEY (report_id)",
                    "FOREIGN KEY (generated_by_user_id) REFERENCES users(user_id)",
                ),
                "contextual_events": (
                    "PRIMARY KEY (event_id)",
                    "UNIQUE (source_context_id)",
                    "FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)",
                ),
            }
            for table_name, fragments in expected_constraint_fragments.items():
                if table_name not in tables:
                    continue
                definitions = [
                    " ".join(
                        value.upper().replace('"', "").replace("PUBLIC.", "").split()
                    )
                    for value in connection.execute(text("""
                        SELECT pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
                        FROM pg_catalog.pg_constraint AS constraint_row
                        JOIN pg_catalog.pg_class AS relation
                          ON relation.oid = constraint_row.conrelid
                        JOIN pg_catalog.pg_namespace AS schema
                          ON schema.oid = relation.relnamespace
                        WHERE schema.nspname = current_schema()
                          AND relation.relname = :table_name
                    """), {"table_name": table_name}).scalars()
                ]
                normalized = [definition.replace('"', "") for definition in definitions]
                missing = [
                    fragment for fragment in fragments
                    if " ".join(
                        fragment.upper().replace("PUBLIC.", "").split()
                    ) not in normalized
                ]
                add_check(
                    f"constraints in {table_name}", not missing,
                    len(definitions), f"includes {len(fragments)} required constraints",
                    "Required keys and foreign keys are present." if not missing
                    else f"{len(missing)} required constraint(s) are absent.",
                )

            if "students" in tables:
                privacy_counts = connection.execute(text("""
                    SELECT
                        COUNT(*) FILTER (
                            WHERE last_name IS NOT NULL OR first_name IS NOT NULL
                               OR email IS NOT NULL OR phone IS NOT NULL OR address IS NOT NULL
                        ) AS rows_with_personal_fields,
                        COUNT(*) FILTER (WHERE id_number !~ '^dev_[0-9a-f]{64}$')
                            AS non_pseudonymous_ids
                    FROM public.students
                """)).mappings().one()
                add_check(
                    "student data pseudonymization",
                    privacy_counts["rows_with_personal_fields"] == 0
                    and privacy_counts["non_pseudonymous_ids"] == 0,
                    {
                        "rows_with_personal_fields": privacy_counts["rows_with_personal_fields"],
                        "non_pseudonymous_ids": privacy_counts["non_pseudonymous_ids"],
                    },
                    {"rows_with_personal_fields": 0, "non_pseudonymous_ids": 0},
                    "Only aggregate checks were run; no student values were returned.",
                )

            if "contextual_events" in tables:
                db_events = connection.execute(text("""
                    SELECT source_context_id, source_year, name, event_type,
                           start_date, start_time, end_date, end_time, all_day
                    FROM public.contextual_events
                    WHERE source = :source_label
                """), {"source_label": SOURCE_LABEL}).mappings().all()
                event_groups = {}
                for row in db_events:
                    event_groups.setdefault(row["source_context_id"], []).append(row)
                missing_ids = set(expected_events) - set(event_groups)
                duplicate_expected_ids = sum(
                    len(event_groups[source_id]) - 1
                    for source_id in set(expected_events) & set(event_groups)
                    if len(event_groups[source_id]) > 1
                )
                unexpected_source_rows = sum(
                    len(rows)
                    for source_id, rows in event_groups.items()
                    if source_id is None or source_id not in expected_events
                )
                mismatches = 0
                fields = (
                    "source_year", "name", "event_type", "start_date",
                    "start_time", "end_date", "end_time", "all_day",
                )
                for source_id, expected in expected_events.items():
                    rows = event_groups.get(source_id, [])
                    if len(rows) == 1 and any(
                        rows[0][field] != expected[field] for field in fields
                    ):
                        mismatches += 1
                add_check(
                    "context source IDs and event fields",
                    not missing_ids and duplicate_expected_ids == 0 and mismatches == 0,
                    {
                        "expected_source_records_found": len(expected_events) - len(missing_ids),
                        "duplicate_expected_source_rows": duplicate_expected_ids,
                        "field_mismatches": mismatches,
                    },
                    {"source_records": len(expected_events), "duplicate_rows": 0, "field_mismatches": 0},
                    "Each expected source ID must occur once with matching event fields; IDs are not emitted.",
                )
                checks.append({
                    "check": "unexpected source-labelled contextual events",
                    "status": "WARNING" if unexpected_source_rows else "PASS",
                    "observed": {"unexpected_rows": unexpected_source_rows},
                    "expected": {"unexpected_rows": 0},
                    "explanation": (
                        "Extra records carrying the CSV importer source label are reported separately. "
                        "Records with other sources (including manually created events) are not rejected."
                    ),
                })

            if "users" in tables:
                user_fk = connection.execute(text("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_constraint AS constraint_row
                        JOIN pg_catalog.pg_class AS relation
                          ON relation.oid = constraint_row.conrelid
                        WHERE relation.relname = 'users'
                          AND relation.relnamespace = current_schema()::regnamespace
                          AND constraint_row.contype = 'f'
                          AND pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
                              ILIKE '%FOREIGN KEY (vendor_id)%'
                    )
                """)).scalar_one()
                checks.append({
                    "check": "legacy users.vendor_id foreign key",
                    "status": "WARNING" if user_fk else "NOT CHECKED",
                    "observed": "present" if user_fk else "not found",
                    "expected": "open BRD decision",
                    "explanation": (
                        "The current application uses this legacy FK; BRD v2 says supporting "
                        "vendor references should not FK into original tables. No change was made."
                    ),
                })

            transaction.rollback()
        except SQLAlchemyError:
            transaction.rollback()
            raise

    result = {
        "database": identity["database_name"],
        "schema": identity["schema_name"],
        "read_only": True,
        "checks": checks,
        "summary": {
            status: sum(1 for check in checks if check["status"] == status)
            for status in ("PASS", "FAIL", "WARNING", "NOT CHECKED")
        },
        "individual_student_or_transaction_records_emitted": False,
    }
    print(json.dumps(result, indent=2, default=str))
    return 1 if result["summary"]["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
