"""Explicit, transactional replacement importer for the reviewed synthetic pack.

The script is inert unless invoked with --replace-business-data,
--confirm-target synthetic-data-dev, and matching target settings in the
environment. It never prints DATABASE_URL, target host, or source student data.

Student IDs are deterministic HMAC pseudonyms. Set
BYTEBITE_STUDENT_ID_HMAC_KEY to a private, stable key outside source control;
the same key is required for every import intended to preserve those IDs.
Names, email, phone, and street address are deliberately not imported.

The importer refuses to replace vendors if existing user/supporting records
refer to them. Resolve those references explicitly before a future run.
All replacement deletes/inserts and contextual-event upserts use one database
transaction. Replacing the four business tables is destructive. Failures
before commit roll back transactional row changes, but recovery of previous
rows after commit is not guaranteed. This script also updates matching
source-keyed rows or inserts missing rows in contextual_events, and advances
the business-table sequences; it does not modify the legacy context_events
table. PostgreSQL sequence advancement is not transactional and may leave
harmless ID gaps after rollback.
"""

import argparse
import csv
import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import monotonic

from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

import database
import models


EXPECTED_BRANCH = "synthetic-data-dev"
BACKEND = Path(__file__).resolve().parent
DATA_DIRECTORY = BACKEND / "data" / "raw" / "Byte_&_Bite Data Pack"
CONTEXT_DIRECTORY = BACKEND / "data" / "raw" / "context"
SOURCE_COUNTS = {
    "Student.csv": 12_000,
    "Vendor_Type.csv": 7,
    "Vendor.csv": 160,
    "Transaction.csv": 4_075_965,
    "context_events_2023.csv": 67,
    "context_events_2024.csv": 59,
    "context_events_2025.csv": 65,
}
TRANSACTION_PROGRESS_INTERVAL = 100_000
SOURCE_LABEL = "Byte & Bite context dataset"
TRANSACTION_ID_VALIDATION_BATCH_SIZE = 20_000
DATA_HEADERS = {
    "Student.csv": {
        "id_number", "last_name", "first_name", "dob", "gender",
        "email", "phone", "address",
    },
    "Vendor_Type.csv": {"type_id", "name"},
    "Vendor.csv": {"vendor_id", "name", "address", "gps", "type_id"},
    "Transaction.csv": {
        "transaction_id", "student_id", "vendor_id", "datetime", "value", "discount",
    },
}
EVENT_HEADERS = {
    "context_id", "year", "category", "subcategory", "title", "start_date",
    "start_time", "end_date", "end_time", "all_day", "location", "campus",
    "faculty", "scope", "source_organisation", "source_name", "source_file",
    "source_url", "source_page", "verification_status", "notes",
}
OPTIONAL_EVENT_TEXT = (
    "subcategory", "location", "campus", "faculty", "scope",
    "source_organisation", "source_name", "source_file", "source_url",
    "source_page", "verification_status", "notes",
)


class SourceValidationError(Exception):
    def __init__(self, issues: Counter):
        self.issues = issues
        super().__init__("Source validation failed.")


def fail(message: str) -> None:
    raise RuntimeError(f"Import stopped: {message}")


def check_target(confirm_target: str) -> None:
    if confirm_target != EXPECTED_BRANCH:
        fail(f"Pass --confirm-target {EXPECTED_BRANCH} to continue.")
    if os.getenv("BYTEBITE_TARGET_BRANCH") != EXPECTED_BRANCH:
        fail(f"BYTEBITE_TARGET_BRANCH must be {EXPECTED_BRANCH}.")

    expected_host = os.getenv("BYTEBITE_DEV_DB_HOST")
    expected_database = os.getenv("BYTEBITE_DEV_DB_NAME")
    if not expected_host or not expected_database:
        fail("Set BYTEBITE_DEV_DB_HOST and BYTEBITE_DEV_DB_NAME first.")
    if database.engine.url.host != expected_host:
        fail("DATABASE_URL host does not match BYTEBITE_DEV_DB_HOST.")
    if database.engine.url.database != expected_database:
        fail("DATABASE_URL database does not match BYTEBITE_DEV_DB_NAME.")
    if not os.getenv("BYTEBITE_STUDENT_ID_HMAC_KEY"):
        fail("BYTEBITE_STUDENT_ID_HMAC_KEY is required and must remain private.")


def read_csv(path: Path, required_headers: set[str]):
    if not path.is_file():
        raise FileNotFoundError(f"Required source file is missing: {path.name}")
    source = path.open("r", encoding="utf-8-sig", newline="")
    reader = csv.DictReader(source)
    actual_headers = set(reader.fieldnames or ())
    if actual_headers != required_headers:
        source.close()
        missing = required_headers - actual_headers
        extra = actual_headers - required_headers
        raise ValueError(
            f"{path.name} headers differ from the reviewed source; "
            f"missing={len(missing)}, extra={len(extra)}"
        )
    return source, reader


def source_file_paths() -> dict[str, Path]:
    paths = {
        filename: DATA_DIRECTORY / filename
        for filename in (
            "Student.csv", "Vendor_Type.csv", "Vendor.csv", "Transaction.csv",
        )
    }
    paths.update({
        filename: CONTEXT_DIRECTORY / filename
        for filename in (
            "context_events_2023.csv",
            "context_events_2024.csv",
            "context_events_2025.csv",
        )
    })
    return paths


def fingerprint_source_files() -> dict[str, str]:
    fingerprints = {}
    for filename, path in source_file_paths().items():
        if not path.is_file():
            fail(f"Required source file is missing: {filename}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        fingerprints[filename] = digest.hexdigest()
    return fingerprints


def verify_source_fingerprints(expected: dict[str, str]) -> None:
    if fingerprint_source_files() != expected:
        fail("A source CSV changed after validation; no import should be committed.")


def text_value(row: dict, field: str, required: bool = False) -> str | None:
    value = (row.get(field) or "").strip()
    if required and not value:
        raise ValueError(f"{field} is required")
    return value or None


def pseudonym(source_id: str, key: bytes) -> str:
    digest = hmac.new(key, source_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"dev_{digest}"


def parse_integer(value: str | None, field: str) -> int:
    try:
        return int(value or "")
    except ValueError as error:
        raise ValueError(f"{field} must be an integer") from error


def parse_date(value: str | None, field: str) -> date:
    try:
        return date.fromisoformat(value or "")
    except ValueError as error:
        raise ValueError(f"{field} must be YYYY-MM-DD") from error


def parse_datetime(value: str | None, field: str) -> datetime:
    try:
        parsed = datetime.strptime(value or "", "%Y-%m-%d %H:%M:%S")
    except ValueError as error:
        raise ValueError(f"{field} must be YYYY-MM-DD HH:MM:SS") from error
    if parsed.tzinfo is not None:
        raise ValueError(f"{field} must not contain a timezone")
    return parsed


def parse_decimal(value: str | None, field: str) -> Decimal:
    try:
        result = Decimal(value or "")
    except InvalidOperation as error:
        raise ValueError(f"{field} must be numeric") from error
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def parse_optional_time(value: str | None, field: str) -> time | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        parsed = time.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{field} must be a valid time") from error
    if parsed.tzinfo is not None:
        raise ValueError(f"{field} must not include a timezone")
    return parsed


def parse_optional_bool(value: str | None, field: str) -> bool | None:
    normalized = (value or "").strip().casefold()
    if not normalized:
        return None
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{field} must be true, false, or blank")


def event_values(row: dict, expected_year: int) -> dict:
    source_id = text_value(row, "context_id", required=True)
    category = text_value(row, "category", required=True)
    name = text_value(row, "title", required=True)
    source_year = parse_integer(row.get("year"), "year")
    if source_year != expected_year:
        raise ValueError("year does not match source filename")

    start_date = parse_date(row.get("start_date"), "start_date")
    end_date = parse_date(row.get("end_date"), "end_date")
    if end_date < start_date:
        raise ValueError("end_date precedes start_date")
    values = {
        "source_context_id": source_id,
        "source_year": source_year,
        "name": name,
        "event_type": category,
        "subcategory": text_value(row, "subcategory"),
        "start_date": start_date,
        "start_time": parse_optional_time(row.get("start_time"), "start_time"),
        "end_date": end_date,
        "end_time": parse_optional_time(row.get("end_time"), "end_time"),
        "all_day": parse_optional_bool(row.get("all_day"), "all_day"),
        "source": SOURCE_LABEL,
        "created_by_user_id": None,
        "updated_at": datetime.now(timezone.utc),
    }
    for field in OPTIONAL_EVENT_TEXT:
        if field != "subcategory":
            values[field] = text_value(row, field)
    return values


def read_small_sources(hmac_key: bytes, issues: Counter):
    students_by_source_id = {}
    student_rows = []
    source = None
    try:
        source, reader = read_csv(DATA_DIRECTORY / "Student.csv", DATA_HEADERS["Student.csv"])
        for row in reader:
            try:
                source_id = text_value(row, "id_number", required=True)
                if source_id in students_by_source_id:
                    raise ValueError("duplicate student key")
                values = {
                    "id_number": pseudonym(source_id, hmac_key),
                    "dob": parse_date(row.get("dob"), "dob"),
                    "gender": text_value(row, "gender"),
                    "last_name": None,
                    "first_name": None,
                    "email": None,
                    "phone": None,
                    "address": None,
                }
                students_by_source_id[source_id] = values["id_number"]
                student_rows.append(values)
            except ValueError as error:
                issues[f"Student.csv: {error}"] += 1
    finally:
        if source is not None:
            source.close()
    if len(student_rows) != SOURCE_COUNTS["Student.csv"]:
        issues["Student.csv: row count differs from reviewed source"] += abs(
            SOURCE_COUNTS["Student.csv"] - len(student_rows)
        ) or 1

    type_rows = []
    source = None
    try:
        source, reader = read_csv(DATA_DIRECTORY / "Vendor_Type.csv", DATA_HEADERS["Vendor_Type.csv"])
        seen = set()
        for row in reader:
            try:
                type_id = parse_integer(row.get("type_id"), "type_id")
                name = text_value(row, "name", required=True)
                if type_id in seen:
                    raise ValueError("duplicate vendor type key")
                seen.add(type_id)
                type_rows.append({"type_id": type_id, "name": name})
            except ValueError as error:
                issues[f"Vendor_Type.csv: {error}"] += 1
    finally:
        if source is not None:
            source.close()
    if len(type_rows) != SOURCE_COUNTS["Vendor_Type.csv"]:
        issues["Vendor_Type.csv: row count differs from reviewed source"] += abs(
            SOURCE_COUNTS["Vendor_Type.csv"] - len(type_rows)
        ) or 1
    known_type_ids = {row["type_id"] for row in type_rows}

    vendor_rows = []
    source = None
    try:
        source, reader = read_csv(DATA_DIRECTORY / "Vendor.csv", DATA_HEADERS["Vendor.csv"])
        seen = set()
        for row in reader:
            try:
                vendor_id = parse_integer(row.get("vendor_id"), "vendor_id")
                type_id = parse_integer(row.get("type_id"), "type_id")
                if vendor_id in seen:
                    raise ValueError("duplicate vendor key")
                if type_id not in known_type_ids:
                    raise ValueError("unknown vendor type reference")
                values = {
                    "vendor_id": vendor_id,
                    "name": text_value(row, "name", required=True),
                    "address": text_value(row, "address"),
                    "gps": text_value(row, "gps"),
                    "type_id": type_id,
                }
                if not values["gps"] or not re.fullmatch(
                    r"POINT\([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
                    r"\s+[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\)",
                    values["gps"],
                ):
                    raise ValueError("gps is not a WKT POINT")
                seen.add(vendor_id)
                vendor_rows.append(values)
            except ValueError as error:
                issues[f"Vendor.csv: {error}"] += 1
    finally:
        if source is not None:
            source.close()
    if len(vendor_rows) != SOURCE_COUNTS["Vendor.csv"]:
        issues["Vendor.csv: row count differs from reviewed source"] += abs(
            SOURCE_COUNTS["Vendor.csv"] - len(vendor_rows)
        ) or 1
    vendor_ids = {row["vendor_id"] for row in vendor_rows}
    return students_by_source_id, student_rows, type_rows, vendor_rows, vendor_ids


def validate_sources(hmac_key: bytes):
    fingerprints = fingerprint_source_files()
    issues = Counter()
    (
        students_by_source_id,
        student_rows,
        type_rows,
        vendor_rows,
        vendor_ids,
    ) = read_small_sources(hmac_key, issues)
    event_rows = []
    seen_context_ids = set()

    for year in (2023, 2024, 2025):
        filename = f"context_events_{year}.csv"
        source = None
        try:
            source, reader = read_csv(CONTEXT_DIRECTORY / filename, EVENT_HEADERS)
            for row in reader:
                try:
                    values = event_values(row, year)
                    key = values["source_context_id"]
                    if key in seen_context_ids:
                        raise ValueError("duplicate context source key")
                    seen_context_ids.add(key)
                    event_rows.append(values)
                except ValueError as error:
                    issues[f"{filename}: {error}"] += 1
        finally:
            if source is not None:
                source.close()
        if sum(1 for row in event_rows if row["source_year"] == year) != SOURCE_COUNTS[filename]:
            issues[f"{filename}: row count differs from reviewed source"] += 1

    with tempfile.TemporaryDirectory(prefix="bytebite-source-check-") as temp_dir:
        index_path = Path(temp_dir) / "transaction_ids.sqlite"
        index = sqlite3.connect(index_path)
        index.execute("PRAGMA journal_mode = OFF")
        index.execute("PRAGMA synchronous = OFF")
        index.execute("CREATE TABLE seen_ids (transaction_id INTEGER PRIMARY KEY)")
        transaction_count = 0
        pending_transaction_ids = []
        source = None

        def flush_transaction_ids():
            if not pending_transaction_ids:
                return
            changes_before = index.total_changes
            index.executemany(
                "INSERT OR IGNORE INTO seen_ids(transaction_id) VALUES (?)",
                ((transaction_id,) for transaction_id in pending_transaction_ids),
            )
            duplicate_count = (
                len(pending_transaction_ids) - (index.total_changes - changes_before)
            )
            if duplicate_count:
                issues["Transaction.csv: duplicate transaction key"] += duplicate_count
            pending_transaction_ids.clear()

        try:
            source, reader = read_csv(
                DATA_DIRECTORY / "Transaction.csv",
                DATA_HEADERS["Transaction.csv"],
            )
            for row in reader:
                transaction_count += 1
                try:
                    transaction_id = parse_integer(
                        row.get("transaction_id"), "transaction_id"
                    )
                    source_student_id = text_value(
                        row, "student_id", required=True
                    )
                    vendor_id = parse_integer(row.get("vendor_id"), "vendor_id")
                    parse_datetime(row.get("datetime"), "datetime")
                    value = parse_decimal(row.get("value"), "value")
                    discount = parse_decimal(row.get("discount"), "discount")
                    if value < 0:
                        raise ValueError("value must not be negative")
                    if discount < 0:
                        raise ValueError("discount must not be negative")
                    if source_student_id not in students_by_source_id:
                        raise ValueError("unknown student reference")
                    if vendor_id not in vendor_ids:
                        raise ValueError("unknown vendor reference")
                    pending_transaction_ids.append(transaction_id)
                    if len(pending_transaction_ids) >= TRANSACTION_ID_VALIDATION_BATCH_SIZE:
                        flush_transaction_ids()
                except ValueError as error:
                    issues[f"Transaction.csv: {error}"] += 1
            flush_transaction_ids()
        finally:
            if source is not None:
                source.close()
            index.close()
    if transaction_count != SOURCE_COUNTS["Transaction.csv"]:
        issues["Transaction.csv: row count differs from reviewed source"] += abs(
            SOURCE_COUNTS["Transaction.csv"] - transaction_count
        ) or 1

    if issues:
        raise SourceValidationError(issues)
    if fingerprint_source_files() != fingerprints:
        fail("A source CSV changed during validation; validation was discarded.")
    return {
        "students": student_rows,
        "vendor_types": type_rows,
        "vendors": vendor_rows,
        "events": event_rows,
        "transaction_count": transaction_count,
        "source_fingerprints": fingerprints,
    }


def get_count(connection, table_name: str) -> int:
    return connection.execute(
        text(f"SELECT COUNT(*) FROM public.{table_name}")
    ).scalar_one()


def ensure_no_vendor_references(connection) -> None:
    checks = {
        "users.vendor_id": "SELECT COUNT(*) FROM public.users WHERE vendor_id IS NOT NULL",
        "user_vendor_links": "SELECT COUNT(*) FROM public.user_vendor_links",
        "notifications.vendor_id": "SELECT COUNT(*) FROM public.notifications WHERE vendor_id IS NOT NULL",
        "report_exports.vendor_id": "SELECT COUNT(*) FROM public.report_exports WHERE vendor_id IS NOT NULL",
    }
    for label, query in checks.items():
        count = connection.execute(text(query)).scalar_one()
        if count:
            fail(
                f"{label} contains {count} vendor reference(s). "
                "Resolve supporting-data references before replacing vendors."
            )


def legacy_context_fingerprint(connection) -> tuple[int, str]:
    digest = hashlib.sha256()
    row_count = 0
    rows = connection.execute(text("""
        SELECT context_id, category, subcategory, title,
               start_date, end_date, notes
        FROM public.context_events
        ORDER BY context_id
    """)).mappings()
    for row in rows:
        payload = json.dumps(
            [
                row["context_id"], row["category"], row["subcategory"],
                row["title"], row["start_date"], row["end_date"], row["notes"],
            ],
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        digest.update(len(payload).to_bytes(8, byteorder="big"))
        digest.update(payload)
        row_count += 1
    return row_count, digest.hexdigest()


TRANSACTION_COPY_SQL = """
    COPY public.transactions
        (transaction_id, student_id, vendor_id, datetime, value, discount)
    FROM STDIN
"""


def transaction_copy_row(row: dict, hmac_key: bytes) -> tuple:
    source_student_id = text_value(row, "student_id", required=True)
    return (
        parse_integer(row.get("transaction_id"), "transaction_id"),
        pseudonym(source_student_id, hmac_key),
        parse_integer(row.get("vendor_id"), "vendor_id"),
        parse_datetime(row.get("datetime"), "datetime"),
        parse_decimal(row.get("value"), "value"),
        parse_decimal(row.get("discount"), "discount"),
    )


def bulk_copy_transactions(
    connection,
    csv_path: Path,
    hmac_key: bytes,
    expected_count: int,
    progress_interval: int = TRANSACTION_PROGRESS_INTERVAL,
    progress_callback=None,
) -> int:
    """COPY transaction rows on the existing SQLAlchemy transaction."""
    if progress_interval <= 0:
        raise ValueError("progress_interval must be positive")

    source, reader = read_csv(csv_path, DATA_HEADERS["Transaction.csv"])
    cursor = None
    row_count = 0
    next_progress = progress_interval
    started_at = monotonic()
    report_progress = progress_callback or (
        lambda count, elapsed: print(
            f"Transaction rows processed for COPY: {count:,} "
            f"(elapsed: {elapsed:.1f}s)"
        )
    )

    def transform_rows():
        nonlocal row_count, next_progress
        for source_row in reader:
            values = transaction_copy_row(source_row, hmac_key)
            row_count += 1
            if row_count >= next_progress:
                report_progress(row_count, monotonic() - started_at)
                next_progress += progress_interval
            yield values

    try:
        raw_connection = connection.connection.driver_connection
        cursor = raw_connection.cursor()
        if callable(getattr(cursor, "copy", None)):
            with cursor.copy(TRANSACTION_COPY_SQL) as copy:
                for values in transform_rows():
                    copy.write_row(values)
        elif callable(getattr(cursor, "copy_expert", None)):
            with tempfile.TemporaryFile(
                mode="w+t",
                encoding="utf-8",
                newline="",
            ) as copy_stream:
                writer = csv.writer(copy_stream, lineterminator="\n")
                for values in transform_rows():
                    writer.writerow(values)
                copy_stream.seek(0)
                cursor.copy_expert(
                    TRANSACTION_COPY_SQL.rstrip() + " WITH (FORMAT CSV)",
                    copy_stream,
                )
        else:
            raise RuntimeError("The active PostgreSQL driver does not support COPY.")
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            source.close()

    if row_count != expected_count:
        fail("Transaction row count changed between validation and import.")
    print(
        f"Transaction COPY complete: {row_count:,} rows "
        f"(elapsed: {monotonic() - started_at:.1f}s)"
    )
    return row_count


def replacement_transaction(connection, data: dict, hmac_key: bytes) -> dict:
    required_tables = {
        "user_vendor_links", "notifications", "report_exports", "contextual_events",
    }
    actual_tables = set(connection.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
    """)).scalars())
    missing = required_tables - actual_tables
    if missing:
        fail("Run the separately reviewed schema migration first; supporting tables are missing.")

    schema_name = connection.execute(
        text("SELECT current_schema()")
    ).scalar_one()
    if schema_name != "public":
        fail("The connected session is not using the public schema.")

    ensure_no_vendor_references(connection)
    tracked_tables = (
        "transactions", "students", "vendors", "vendor_types",
        "contextual_events", "context_events",
    )
    before = {table: get_count(connection, table) for table in tracked_tables}
    legacy_before = legacy_context_fingerprint(connection)
    if legacy_before[0] != 191:
        fail("Expected all 191 legacy context_events rows before replacement.")

    connection.execute(text("DELETE FROM public.transactions"))
    connection.execute(text("DELETE FROM public.students"))
    connection.execute(text("DELETE FROM public.vendors"))
    connection.execute(text("DELETE FROM public.vendor_types"))

    connection.execute(text("""
        INSERT INTO public.vendor_types (type_id, name)
        VALUES (:type_id, :name)
    """), data["vendor_types"])
    connection.execute(text("""
        INSERT INTO public.vendors (vendor_id, name, address, gps, type_id)
        VALUES (:vendor_id, :name, :address, :gps, :type_id)
    """), data["vendors"])
    connection.execute(text("""
        INSERT INTO public.students
            (id_number, last_name, first_name, dob, gender, email, phone, address)
        VALUES
            (:id_number, :last_name, :first_name, :dob, :gender, :email, :phone, :address)
    """), data["students"])

    transaction_rows = bulk_copy_transactions(
        connection,
        DATA_DIRECTORY / "Transaction.csv",
        hmac_key,
        data["transaction_count"],
    )

    # Explicit source IDs require advancing the backing sequences before later
    # application-created records use database-generated identifiers.
    for table_name, key_column in (
        ("vendor_types", "type_id"),
        ("vendors", "vendor_id"),
        ("transactions", "transaction_id"),
    ):
        connection.execute(text(f"""
            SELECT setval(
                pg_get_serial_sequence('public.{table_name}', '{key_column}'),
                COALESCE((SELECT MAX({key_column}) FROM public.{table_name}), 1),
                EXISTS (SELECT 1 FROM public.{table_name})
            )
        """))

    event_table = models.ContextualEvent.__table__
    source_event_ids = [row["source_context_id"] for row in data["events"]]
    source_fields = [
        column.name for column in event_table.columns
        if column.name not in {
            "event_id", "source_context_id", "created_by_user_id", "updated_at",
        }
    ]
    existing_events = {
        row["source_context_id"]: row
        for row in connection.execute(
            select(
                event_table.c.source_context_id,
                *(event_table.c[field] for field in source_fields),
            ).where(event_table.c.source_context_id.in_(source_event_ids))
        ).mappings()
    }
    event_counts = {"imported": 0, "updated": 0, "skipped": 0}
    for event in data["events"]:
        existing = existing_events.get(event["source_context_id"])
        if existing is None:
            event_counts["imported"] += 1
        elif any(existing[field] != event[field] for field in source_fields):
            event_counts["updated"] += 1
        else:
            event_counts["skipped"] += 1

    event_insert = pg_insert(event_table).values(data["events"])
    update_fields = {
        column.name: getattr(event_insert.excluded, column.name)
        for column in event_table.columns
        if column.name not in {
            "event_id", "source_context_id", "created_by_user_id", "updated_at",
        }
    }
    changed_fields = [
        event_table.c[field].is_distinct_from(getattr(event_insert.excluded, field))
        for field in source_fields
    ]
    update_fields["updated_at"] = datetime.now(timezone.utc)
    connection.execute(
        event_insert.on_conflict_do_update(
            index_elements=[event_table.c.source_context_id],
            set_=update_fields,
            where=or_(*changed_fields),
        )
    )

    after = {table: get_count(connection, table) for table in tracked_tables}
    legacy_after = legacy_context_fingerprint(connection)
    if legacy_after != legacy_before:
        fail("Legacy context_events fingerprint changed; transaction will roll back.")
    if after["transactions"] != SOURCE_COUNTS["Transaction.csv"]:
        fail("Final transaction count does not match the validated source.")
    if after["students"] != SOURCE_COUNTS["Student.csv"]:
        fail("Final student count does not match the validated source.")
    if after["vendors"] != SOURCE_COUNTS["Vendor.csv"]:
        fail("Final vendor count does not match the validated source.")
    if after["vendor_types"] != SOURCE_COUNTS["Vendor_Type.csv"]:
        fail("Final vendor-type count does not match the validated source.")

    return {
        "before": before,
        "after": after,
        "transactions_imported": transaction_rows,
        "students_pseudonymized": len(data["students"]),
        "context_events": event_counts,
        "context_source_records": len(data["events"]),
        "rejected_source_rows": 0,
        "legacy_context_events_preserved": legacy_after[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace-business-data",
        action="store_true",
        help=(
            "Destructively replace rows in the four business tables; "
            "recovery of previous rows after commit is not guaranteed."
        ),
    )
    parser.add_argument(
        "--confirm-target",
        default="",
        help="Must be synthetic-data-dev.",
    )
    args = parser.parse_args()
    if not args.replace_business_data:
        parser.error("No action taken. Explicit --replace-business-data is required.")

    check_target(args.confirm_target)
    hmac_key = os.environ["BYTEBITE_STUDENT_ID_HMAC_KEY"].encode("utf-8")
    if len(hmac_key) < 32:
        fail("BYTEBITE_STUDENT_ID_HMAC_KEY must be at least 32 bytes.")
    try:
        data = validate_sources(hmac_key)
    except SourceValidationError as error:
        print(json.dumps({
            "status": "rejected",
            "issue_counts_by_reason": dict(sorted(error.issues.items())),
            "individual_rows_emitted": False,
        }, indent=2))
        return 2

    try:
        with database.engine.begin() as connection:
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()
            if database_name != os.environ["BYTEBITE_DEV_DB_NAME"]:
                fail("Connected database name does not match the expected development database.")
            if connection.execute(
                text("SELECT current_schema()")
            ).scalar_one() != "public":
                fail("The connected session is not using the public schema.")
            verify_source_fingerprints(data["source_fingerprints"])
            summary = replacement_transaction(connection, data, hmac_key)
            verify_source_fingerprints(data["source_fingerprints"])
    except SQLAlchemyError as error:
        print(json.dumps({
            "status": "rolled_back",
            "database_error_type": type(error).__name__,
            "individual_rows_emitted": False,
        }, indent=2))
        return 1

    print(json.dumps({"status": "committed", **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
