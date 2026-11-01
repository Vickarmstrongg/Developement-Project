"""Migrate the cleaned lecturer dataset into the Byte & Bite database.

Nothing here runs unless you ask for it. Sub-commands:

  preflight   Offline CSV validation. Never opens a database connection
              unless --check-db is passed (read-only SELECTs only).
  write-user-mapping-template
              Read-only. Writes the user -> vendor mapping template and a
              vendor reference list into data/migration/.
  init-marker Creates one small marker table on the intended test branch.
              The apply step refuses to run without it.
  apply       Replaces the synthetic business data with the lecturer data in
              ONE transaction. Any failed check rolls everything back.

Design rules
  * The application keeps its integer IDs (vendor_types.type_id,
    vendors.vendor_id, transactions.transaction_id, contextual_events.event_id).
    Lecturer UUIDs are kept in new source_uuid columns (UNIQUE, indexed).
  * students.id_number is already text, so it holds the lecturer student UUID
    directly. No names, dates of birth, contact details or addresses are
    imported: the cleaned student file only has IDs and the importer refuses
    any other column.
  * transactions.value, discount and datetime are copied as text and cast
    inside PostgreSQL, then compared digit-for-digit with the source. Their
    meaning/units are unconfirmed, so no calculation is changed.
  * vendors.gps keeps the existing WKT format: POINT(longitude latitude).
  * The legacy context_events table is never touched.
  * The new columns are NOT added to models.py on purpose, so the app keeps
    working on branches that have not been migrated.

Safety gates for init-marker/apply/write-user-mapping-template/--check-db
  * BYTEBITE_MIGRATION_TARGET must equal lecturer-data-migration-test and the
    same value must be passed with --confirm-target.
  * BYTEBITE_MIGRATION_DB_HOST must equal the host in DATABASE_URL. Neon
    branches can share a database name but each has its own endpoint host, so
    the host (not the database name) identifies the branch.
  * BYTEBITE_MIGRATION_FORBIDDEN_DB_HOSTS (comma separated; MANDATORY: production
    and synthetic-data-dev hosts) must not contain it. The host in
    BYTEBITE_DEV_DB_HOST is always treated as forbidden too.
  * init-marker/apply also need you to type the target name at a prompt.
  * apply additionally needs the marker row created by init-marker; the marker
    stores a fingerprint of the endpoint host and must match it.
  * Sequences are never reset (not transactional); new IDs continue upward.
Hosts, URLs and credentials are never printed.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError

TARGET_NAME = "lecturer-data-migration-test"
MARKER_TABLE = "lecturer_migration_target"
EVENT_SOURCE_LABEL = "Lecturer dataset (cleaned)"
SYNTHETIC_EVENT_SOURCE_LABEL = "Byte & Bite context dataset"

BACKEND = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND.parent
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned"
MIGRATION_DIR = PROJECT_ROOT / "data" / "migration"

FILES = {
    "vendor_type": "vendor_type.csv",
    "vendor": "vendor.csv",
    "student": "student.csv",
    "transaction": "transaction.csv",
    "calendar_event": "calendar_event.csv",
}
HEADERS = {
    "vendor_type": ["id", "name"],
    "vendor": ["id", "name", "address", "latitude", "longitude", "type_id"],
    "student": ["id"],
    "transaction": [
        "id", "student_id", "vendor_id", "tx_datetime", "value", "discount",
    ],
    "calendar_event": [
        "event_id", "event_type", "name", "start_date", "end_date", "scope",
        "recurring",
    ],
}
EXPECTED_COUNTS = {
    "vendor_type": 4,
    "vendor": 90,
    "student": 29_148,
    "transaction": 2_833_658,
    "calendar_event": 113,
}
FOOD_TYPES = {
    "Restaurant", "Cafe / Coffee Shop", "Fast Food & Takeaway",
    "Bakery & Snacks",
}
DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_REPORTED = 10

BUSINESS_TABLES = ["transactions", "students", "vendors", "vendor_types"]
SOURCE_UUID_TABLES = [
    "vendor_types", "vendors", "transactions", "contextual_events",
]


class MigrationError(Exception):
    pass


def stop(message: str) -> None:
    raise MigrationError(message)


# --------------------------------------------------------------------------
# CSV validation (offline)
# --------------------------------------------------------------------------

def is_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower() and value == value.lower()
    except (ValueError, AttributeError):
        return False


def parse_decimal(value: str):
    if not DECIMAL_RE.match(value or ""):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


class Issues:
    """Counts problems and keeps a few anonymous examples (line numbers only)."""

    def __init__(self):
        self.counts = Counter()
        self.examples = {}

    def add(self, name: str, file: str, line: int):
        self.counts[name] += 1
        samples = self.examples.setdefault(name, [])
        if len(samples) < MAX_REPORTED:
            samples.append(f"{file}:{line}")

    def __bool__(self):
        return bool(self.counts)

    def report(self) -> dict:
        return {
            name: {"count": count, "example_lines": self.examples[name]}
            for name, count in sorted(self.counts.items())
        }


def open_csv(path: Path, key: str, issues: Issues):
    if not path.is_file():
        issues.add("missing_file", path.name, 0)
        return None, None
    handle = path.open("r", encoding="utf-8-sig", newline="")
    reader = csv.reader(handle)
    header = next(reader, None)
    if header != HEADERS[key]:
        issues.add("unexpected_columns", path.name, 1)
        handle.close()
        return None, None
    return handle, reader


def validate_sources(cleaned_dir: Path = CLEANED_DIR) -> dict:
    """Validate every file before any database work. Returns a summary."""
    issues = Issues()
    summary = {"files": {}, "issues": {}}

    def read(key):
        return open_csv(cleaned_dir / FILES[key], key, issues)

    # --- vendor types
    type_ids, type_names = set(), {}
    handle, reader = read("vendor_type")
    if reader:
        with handle:
            for line, row in enumerate(reader, start=2):
                if len(row) != 2 or not is_uuid(row[0]) or not row[1].strip():
                    issues.add("vendor_type_malformed", FILES["vendor_type"], line)
                    continue
                if row[0] in type_ids:
                    issues.add("vendor_type_duplicate_id", FILES["vendor_type"], line)
                type_ids.add(row[0])
                type_names[row[0]] = row[1]
        summary["files"]["vendor_type"] = len(type_ids)
        if set(type_names.values()) != FOOD_TYPES:
            issues.add("vendor_type_not_the_four_food_types", FILES["vendor_type"], 0)

    # --- vendors
    vendor_ids, vendor_rows = set(), 0
    handle, reader = read("vendor")
    if reader:
        with handle:
            for line, row in enumerate(reader, start=2):
                vendor_rows += 1
                if len(row) != 6 or not is_uuid(row[0]) or not row[1].strip():
                    issues.add("vendor_malformed", FILES["vendor"], line)
                    continue
                if row[0] in vendor_ids:
                    issues.add("vendor_duplicate_id", FILES["vendor"], line)
                vendor_ids.add(row[0])
                if row[5] not in type_ids:
                    issues.add("vendor_unknown_type", FILES["vendor"], line)
                lat, lon = parse_decimal(row[3]), parse_decimal(row[4])
                if lat is None or lon is None or not (-90 <= lat <= 90) \
                        or not (-180 <= lon <= 180):
                    issues.add("vendor_bad_coordinates", FILES["vendor"], line)
        summary["files"]["vendor"] = vendor_rows

    # --- students (IDs only)
    student_ids = set()
    handle, reader = read("student")
    if reader:
        with handle:
            for line, row in enumerate(reader, start=2):
                if len(row) != 1 or not is_uuid(row[0]):
                    issues.add("student_malformed", FILES["student"], line)
                    continue
                if row[0] in student_ids:
                    issues.add("student_duplicate_id", FILES["student"], line)
                student_ids.add(row[0])
        summary["files"]["student"] = len(student_ids)

    # --- calendar events
    event_ids, event_rows = set(), 0
    handle, reader = read("calendar_event")
    if reader:
        with handle:
            for line, row in enumerate(reader, start=2):
                event_rows += 1
                if len(row) != 7 or not is_uuid(row[0]) or not row[1].strip() \
                        or not row[2].strip():
                    issues.add("event_malformed", FILES["calendar_event"], line)
                    continue
                if row[0] in event_ids:
                    issues.add("event_duplicate_id", FILES["calendar_event"], line)
                event_ids.add(row[0])
                try:
                    start = datetime.strptime(row[3], "%Y-%m-%d").date()
                    end = datetime.strptime(row[4], "%Y-%m-%d").date()
                    if end < start:
                        issues.add("event_end_before_start", FILES["calendar_event"], line)
                except ValueError:
                    issues.add("event_bad_date", FILES["calendar_event"], line)
                if row[6] not in ("true", "false"):
                    issues.add("event_bad_recurring_flag", FILES["calendar_event"], line)
        summary["files"]["calendar_event"] = event_rows

    # --- transactions (streamed; only IDs are kept in memory)
    tx_ids = set()
    total_value, total_discount = Decimal(0), Decimal(0)
    tx_rows, earliest, latest = 0, None, None
    seen_students, seen_vendors = set(), set()
    handle, reader = read("transaction")
    if reader:
        with handle:
            for line, row in enumerate(reader, start=2):
                tx_rows += 1
                if len(row) != 6 or not all(is_uuid(row[i]) for i in range(3)):
                    issues.add("transaction_malformed", FILES["transaction"], line)
                    continue
                key = uuid.UUID(row[0]).bytes
                if key in tx_ids:
                    issues.add("transaction_duplicate_id", FILES["transaction"], line)
                tx_ids.add(key)
                if row[1] not in student_ids:
                    issues.add("transaction_unknown_student", FILES["transaction"], line)
                seen_students.add(row[1])
                if row[2] not in vendor_ids:
                    issues.add("transaction_unknown_vendor", FILES["transaction"], line)
                seen_vendors.add(row[2])
                try:
                    moment = datetime.strptime(row[3], DATETIME_FORMAT)
                    if earliest is None or moment < earliest:
                        earliest = moment
                    if latest is None or moment > latest:
                        latest = moment
                except ValueError:
                    issues.add("transaction_bad_datetime", FILES["transaction"], line)
                value, discount = parse_decimal(row[4]), parse_decimal(row[5])
                if value is None:
                    issues.add("transaction_bad_value", FILES["transaction"], line)
                else:
                    total_value += value
                if discount is None:
                    issues.add("transaction_bad_discount", FILES["transaction"], line)
                else:
                    total_discount += discount
        summary["files"]["transaction"] = tx_rows
        summary["transactions"] = {
            "distinct_ids": len(tx_ids),
            "sum_value": str(total_value),
            "sum_discount": str(total_discount),
            "earliest": earliest.strftime(DATETIME_FORMAT) if earliest else None,
            "latest": latest.strftime(DATETIME_FORMAT) if latest else None,
            "distinct_students_used": len(seen_students),
            "distinct_vendors_used": len(seen_vendors),
        }
    del tx_ids

    for key, expected in EXPECTED_COUNTS.items():
        actual = summary["files"].get(key)
        if actual is not None and actual != expected:
            issues.add(f"{key}_count_differs_from_expected_{expected}", FILES[key], 0)

    summary["issues"] = issues.report()
    summary["ok"] = not issues
    summary["_vendor_ids"] = vendor_ids  # internal; stripped before printing
    return summary


def public_summary(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if not k.startswith("_")}


# --------------------------------------------------------------------------
# User -> vendor mapping
# --------------------------------------------------------------------------

MAPPING_HEADERS = [
    "user_id", "email", "role", "status", "current_vendor_link_count",
    "vendor_source_uuid",
]


def load_user_mapping(path: Path, valid_vendor_uuids: set) -> dict:
    """Return {user_id: {"role": str, "vendors": [uuid, ...]}} or raise."""
    if not path.is_file():
        stop("The user vendor mapping file does not exist.")
    problems = []
    mapping = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or any(
            h not in reader.fieldnames for h in ("user_id", "role", "vendor_source_uuid")
        ):
            stop("Mapping file needs the columns user_id, role, vendor_source_uuid.")
        for line, row in enumerate(reader, start=2):
            user_part = (row.get("user_id") or "").strip()
            role = (row.get("role") or "").strip()
            vendor = (row.get("vendor_source_uuid") or "").strip().lower()
            if not user_part.isdigit():
                problems.append(f"line {line}: user_id must be an integer")
                continue
            if role not in ("Manager", "Staff"):
                problems.append(f"line {line}: role must be Manager or Staff")
                continue
            if not vendor:
                problems.append(f"line {line}: vendor_source_uuid is blank")
                continue
            if vendor not in valid_vendor_uuids:
                problems.append(f"line {line}: vendor_source_uuid is not in vendor.csv")
                continue
            entry = mapping.setdefault(int(user_part), {"role": role, "vendors": []})
            if entry["role"] != role:
                problems.append(f"line {line}: user has conflicting roles in the file")
            if vendor in entry["vendors"]:
                problems.append(f"line {line}: duplicate vendor for the same user")
            entry["vendors"].append(vendor)
    for user_id, entry in mapping.items():
        if entry["role"] == "Staff" and len(entry["vendors"]) != 1:
            problems.append(f"user {user_id}: Staff must have exactly one vendor")
        if entry["role"] == "Manager" and not entry["vendors"]:
            problems.append(f"user {user_id}: Manager needs at least one vendor")
    if problems:
        stop("User mapping problems:\n  " + "\n  ".join(problems[:30]))
    return mapping


# --------------------------------------------------------------------------
# Database safety
# --------------------------------------------------------------------------

def _normal_host(host) -> str:
    return (host or "").strip().lower().replace("-pooler", "")


def host_fingerprint(host) -> str:
    return hashlib.sha256(_normal_host(host).encode("utf-8")).hexdigest()


def check_target(confirm_target: str, require_direct: bool = False):
    """Refuse unless the connection is the declared migration-test branch.

    Neon exposes no SQL-visible branch name, so the endpoint host is the only
    reliable branch identifier. It is checked three ways: it must equal the
    host you declare, it must not be on a mandatory deny-list, and (for writes)
    it must match the fingerprint stored in the marker table.
    """
    if confirm_target != TARGET_NAME:
        stop(f"Pass --confirm-target {TARGET_NAME}.")
    if os.getenv("BYTEBITE_MIGRATION_TARGET") != TARGET_NAME:
        stop(f"Set BYTEBITE_MIGRATION_TARGET={TARGET_NAME}.")
    if os.getenv("BYTEBITE_TARGET_BRANCH") == "synthetic-data-dev":
        stop("BYTEBITE_TARGET_BRANCH=synthetic-data-dev is set; this session is "
             "configured for another branch. Remove it and try again.")
    declared = _normal_host(os.getenv("BYTEBITE_MIGRATION_DB_HOST"))
    if not declared:
        stop("Set BYTEBITE_MIGRATION_DB_HOST to the host of the test branch.")
    denied = {
        _normal_host(h)
        for h in os.getenv("BYTEBITE_MIGRATION_FORBIDDEN_DB_HOSTS", "").split(",")
        if h.strip()
    }
    if not denied:
        stop("Set BYTEBITE_MIGRATION_FORBIDDEN_DB_HOSTS to the hosts of production "
             "and synthetic-data-dev (comma separated). It is mandatory.")
    import database  # imported late so offline preflight needs no DATABASE_URL

    if require_direct and "-pooler" in (database.engine.url.host or "").lower():
        stop("DATABASE_URL uses a pooled (-pooler) Neon host. Use the direct connection "
             "string (Connection pooling OFF) for apply.")
    actual = _normal_host(database.engine.url.host)
    if actual != declared:
        stop("DATABASE_URL host does not match BYTEBITE_MIGRATION_DB_HOST.")
    # The existing importers keep the synthetic-data-dev host in this variable.
    denied.add(_normal_host(os.getenv("BYTEBITE_DEV_DB_HOST")))
    denied.discard("")
    if actual in denied:
        stop("The connected host is on the deny list (or equals BYTEBITE_DEV_DB_HOST, "
             "the synthetic-data-dev host). Check DATABASE_URL points at the test branch.")
    return database.engine


def confirm_interactively(action: str):
    """A human must type the target name; this blocks scripted/accidental runs."""
    if not sys.stdin or not sys.stdin.isatty():
        stop("Interactive confirmation is required; run this in a terminal.")
    typed = input(f"Type {TARGET_NAME} to {action}: ").strip()
    if typed != TARGET_NAME:
        stop("Confirmation text did not match; nothing was changed.")


def require_marker(connection):
    """The marker proves init-marker was run on THIS endpoint."""
    if not table_exists(connection, MARKER_TABLE):
        stop("Target marker missing. Run init-marker on the test branch first.")
    row = connection.execute(
        text(f"SELECT host_hash FROM public.{MARKER_TABLE} WHERE target_name = :t"),
        {"t": TARGET_NAME},
    ).first()
    if not row:
        stop("Target marker missing. Run init-marker on the test branch first.")
    if row[0] != host_fingerprint(connection.engine.url.host):
        stop("The marker was created for a different database endpoint.")


# Foreign keys that may point at the four business tables. Anything else, or
# any ON DELETE action other than NO ACTION/RESTRICT, aborts the migration.
ALLOWED_FOREIGN_KEYS = {
    ("transactions", "students"), ("transactions", "vendors"),
    ("vendors", "vendor_types"), ("users", "vendors"),
}
ID_COLUMNS = [
    ("vendor_types", "type_id"), ("vendors", "vendor_id"),
    ("transactions", "transaction_id"), ("contextual_events", "event_id"),
]
EXPECTED_DATA_TYPES = {
    ("transactions", "datetime"): {"timestamp without time zone"},
    ("transactions", "value"): {"numeric"},
    ("transactions", "discount"): {"numeric"},
    ("transactions", "student_id"): {"text", "character varying"},
    ("students", "id_number"): {"text", "character varying"},
    ("vendors", "gps"): {"text", "character varying"},
    ("contextual_events", "start_date"): {"date"},
    ("contextual_events", "end_date"): {"date"},
}


def unexpected_foreign_keys(rows) -> list:
    """rows: (child_table, parent_table, on_delete_code)."""
    problems = []
    for child, parent, on_delete in rows:
        if (child, parent) not in ALLOWED_FOREIGN_KEYS:
            problems.append(f"unexpected foreign key {child} -> {parent}")
        elif on_delete not in ("a", "r"):
            problems.append(f"{child} -> {parent} has a cascading/SET NULL delete rule")
    return problems


def schema_problems(connection) -> list:
    problems = []
    if connection.execute(text("SELECT current_schema()")).scalar() != "public":
        problems.append("current schema is not public")
    for (table, column), allowed in EXPECTED_DATA_TYPES.items():
        got = connection.execute(text(
            "SELECT data_type FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = :t AND column_name = :c"
        ), {"t": table, "c": column}).scalar()
        if got not in allowed:
            problems.append(f"{table}.{column} has type {got!r}, expected one of {sorted(allowed)}")
    for table, column in ID_COLUMNS:
        row = connection.execute(text(
            "SELECT column_default IS NOT NULL OR is_identity = 'YES' FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
        ), {"t": table, "c": column}).scalar()
        if not row:
            problems.append(f"{table}.{column} has no auto-generated default")
    rows = connection.execute(text(
        "SELECT conrelid::regclass::text, confrelid::regclass::text, confdeltype::text "
        "FROM pg_constraint WHERE contype = 'f' AND confrelid IN ("
        "'public.vendors'::regclass, 'public.students'::regclass, "
        "'public.transactions'::regclass, 'public.vendor_types'::regclass)"
    )).all()
    clean = [(c.replace("public.", ""), p.replace("public.", ""), d) for c, p, d in rows]
    problems.extend(unexpected_foreign_keys(clean))
    return problems


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

def table_count(connection, table: str) -> int:
    return connection.execute(text(f"SELECT count(*) FROM public.{table}")).scalar()


def column_exists(connection, table: str, column: str) -> bool:
    return bool(connection.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
        "AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).first())


def table_exists(connection, table: str) -> bool:
    return bool(connection.execute(
        text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{table}"}
    ).scalar())


def read_only_db_report(connection) -> dict:
    required = BUSINESS_TABLES + [
        "users", "user_vendor_links", "notifications", "report_exports",
        "contextual_events",
    ]
    missing = [t for t in required if not table_exists(connection, t)]
    if missing:
        return {"missing_tables": missing}
    report = {"row_counts": {t: table_count(connection, t) for t in required}}
    report["source_uuid_columns_present"] = {
        t: column_exists(connection, t, "source_uuid") for t in SOURCE_UUID_TABLES
    }
    report["users_by_role"] = dict(connection.execute(text(
        "SELECT role, count(*) FROM public.users GROUP BY role"
    )).all())
    report["migration_progress"] = progress_report(connection)
    return report


def read_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader)
        yield from reader


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_preflight(args) -> int:
    summary = validate_sources(Path(args.cleaned_dir))
    valid_vendors = summary["_vendor_ids"]
    result = public_summary(summary)
    if args.user_vendor_map:
        try:
            mapping = load_user_mapping(Path(args.user_vendor_map), valid_vendors)
            result["user_mapping"] = {
                "users": len(mapping),
                "links": sum(len(m["vendors"]) for m in mapping.values()),
            }
        except MigrationError as error:
            result["user_mapping_error"] = str(error)
            result["ok"] = False
    if args.check_db:
        engine = check_target(args.confirm_target)
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            result["database"] = read_only_db_report(connection)
            try:
                require_marker(connection)
                result["database"]["target_marker_matches_endpoint"] = True
            except MigrationError:
                result["database"]["target_marker_matches_endpoint"] = False
            if "row_counts" in result["database"]:
                problems = schema_problems(connection)
                result["database"]["schema_problems"] = problems
                if problems:
                    result["ok"] = False
                if args.user_vendor_map and "user_mapping" in result:
                    mismatches = _mapping_matches_users(connection, mapping)
                    result["database"]["mapping_problems"] = mismatches
                    if mismatches:
                        result["ok"] = False
            else:
                result["ok"] = False
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["ok"] else 1


def _mapping_matches_users(connection, mapping: dict) -> list:
    problems = []
    users = connection.execute(text(
        "SELECT user_id, role FROM public.users WHERE role <> 'Admin'"
    )).all()
    db_roles = {user_id: role for user_id, role in users}
    for user_id in sorted(set(db_roles) - set(mapping)):
        problems.append(f"user {user_id} has no mapping rows")
    for user_id in sorted(set(mapping) - set(db_roles)):
        problems.append(f"mapped user {user_id} is not a non-Admin user in the database")
    for user_id, role in db_roles.items():
        if user_id in mapping and mapping[user_id]["role"] != role:
            problems.append(f"user {user_id}: role in the file differs from the database")
    return problems


def cmd_write_template(args) -> int:
    summary = validate_sources(Path(args.cleaned_dir))
    if not summary["ok"]:
        stop("Fix the CSV problems (run preflight) before creating the template.")
    engine = check_target(args.confirm_target)
    MIGRATION_DIR.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        users = connection.execute(text(
            "SELECT u.user_id, u.email, u.role, u.status, "
            "(SELECT count(*) FROM public.user_vendor_links l WHERE l.user_id = u.user_id) "
            "FROM public.users u WHERE u.role <> 'Admin' ORDER BY u.user_id"
        )).all()
    template = MIGRATION_DIR / "user_vendor_mapping.csv"
    reference = MIGRATION_DIR / "vendor_reference.csv"
    if template.exists() and not args.overwrite_template:
        stop("user_vendor_mapping.csv already exists; pass --overwrite-template to replace it.")
    with template.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(MAPPING_HEADERS)
        for user_id, email, role, status, link_count in users:
            writer.writerow([user_id, email, role, status, link_count, ""])
    types = {row[0]: row[1] for row in read_rows(Path(args.cleaned_dir) / FILES["vendor_type"])}
    with reference.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["vendor_source_uuid", "vendor_name", "vendor_type", "address"])
        for row in read_rows(Path(args.cleaned_dir) / FILES["vendor"]):
            writer.writerow([row[0], row[1], types[row[5]], row[2]])
    print(f"Wrote {template.name} ({len(users)} non-Admin users) and {reference.name}.")
    print("Fill vendor_source_uuid; add extra rows for Managers with several vendors.")
    return 0


def cmd_init_marker(args) -> int:
    engine = check_target(args.confirm_target)
    confirm_interactively("mark this database endpoint as the migration test branch")
    with engine.begin() as connection:
        connection.execute(text(
            f"CREATE TABLE IF NOT EXISTS public.{MARKER_TABLE} ("
            "target_name TEXT PRIMARY KEY, host_hash TEXT NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        connection.execute(text(
            f"INSERT INTO public.{MARKER_TABLE} (target_name, host_hash) VALUES (:t, :h) "
            "ON CONFLICT DO NOTHING"
        ), {"t": TARGET_NAME, "h": host_fingerprint(engine.url.host)})
        require_marker(connection)
    print("Target marker is in place for this endpoint.")
    return 0


STATE_TABLE = "lecturer_migration_state"
BATCH_TABLE = "lecturer_migration_batches"
DEFAULT_BATCH_SIZE = 100_000
DELETE_CHUNK = 100_000
# Bump whenever the migration logic changes: a run started by another version
# cannot be resumed by this one.
MIGRATION_VERSION = "lecturer-batched-v2"
LOCK_KEYS = (1_950_302_117, 20_261_031)  # advisory lock (classid, objid)
CLEARING, LOADING, VALIDATING, COMPLETE = "clearing", "loading", "validating", "complete"

SCHEMA_STATEMENTS = [
    "ALTER TABLE public.vendor_types ADD COLUMN IF NOT EXISTS source_uuid UUID",
    "ALTER TABLE public.vendors ADD COLUMN IF NOT EXISTS source_uuid UUID",
    "ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS source_uuid UUID",
    "ALTER TABLE public.contextual_events ADD COLUMN IF NOT EXISTS source_uuid UUID",
    "ALTER TABLE public.contextual_events ADD COLUMN IF NOT EXISTS recurring BOOLEAN",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_types_source_uuid ON public.vendor_types (source_uuid)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_vendors_source_uuid ON public.vendors (source_uuid)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_source_uuid ON public.transactions (source_uuid)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_contextual_events_source_uuid ON public.contextual_events (source_uuid)",
    f"""CREATE TABLE IF NOT EXISTS public.{STATE_TABLE} (
        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
        status TEXT NOT NULL,
        dataset_fingerprint TEXT NOT NULL,
        batch_size INTEGER NOT NULL,
        total_batches INTEGER NOT NULL,
        users_before INTEGER NOT NULL,
        user_digest_before TEXT NOT NULL,
        replace_synthetic_events BOOLEAN NOT NULL,
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    f"""CREATE TABLE IF NOT EXISTS public.{BATCH_TABLE} (
        batch_no INTEGER PRIMARY KEY,
        row_count INTEGER NOT NULL,
        source_hash TEXT NOT NULL,
        committed_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
]
FINAL_INDEX_STATEMENT = (
    "CREATE INDEX IF NOT EXISTS idx_transactions_vendor_datetime "
    "ON public.transactions (vendor_id, datetime)"
)
LOCKED_TABLES = BUSINESS_TABLES + [
    "users", "user_vendor_links", "notifications", "report_exports", "contextual_events",
]


def gps_wkt(latitude: str, longitude: str) -> str:
    """Existing app format (see rush_hour.parse_gps): POINT(longitude latitude)."""
    return f"POINT({longitude} {latitude})"


def user_digest(connection) -> str:
    """Hash of identity/credential columns, computed in the database, never printed."""
    return connection.execute(text(
        "SELECT md5(COALESCE(string_agg(concat_ws('|', user_id, email, role, status, "
        "password_hash, full_name, locked, failed_login_attempts), ',' ORDER BY user_id), '')) "
        "FROM public.users"
    )).scalar()


def snapshot_before_apply(connection) -> Path:
    """Local record (ids, roles, links only; no emails or hashes) for manual recovery."""
    MIGRATION_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = MIGRATION_DIR / f"pre_migration_snapshot_{stamp}.json"
    users = connection.execute(text(
        "SELECT user_id, role, status, vendor_id FROM public.users ORDER BY user_id"
    )).all()
    links = connection.execute(text(
        "SELECT user_id, vendor_id FROM public.user_vendor_links ORDER BY user_id, vendor_id"
    )).all()
    snapshot = {
        "row_counts": {t: table_count(connection, t) for t in LOCKED_TABLES},
        "users": [list(row) for row in users],
        "links": [list(row) for row in links],
    }
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Resumable batched apply
# --------------------------------------------------------------------------

def migration_engine(base_engine):
    """Dedicated engine: TCP keepalives, and a pool of exactly one connection, so a second
    connection can never be opened by accident (it would time out instead)."""
    from sqlalchemy import create_engine

    return create_engine(
        base_engine.url, pool_pre_ping=True, pool_size=1, max_overflow=0, pool_timeout=5,
        connect_args={
            "connect_timeout": 15, "keepalives": 1, "keepalives_idle": 30,
            "keepalives_interval": 10, "keepalives_count": 5,
        },
    )


def run_once(session, work):
    """Run work(connection) in ONE transaction on the lock-holding connection.

    There is deliberately no retry and no reconnect: if the connection is lost
    the run aborts, and a later run must re-acquire the lock and consult the
    committed ledger before it writes anything.
    """
    with session.begin() as connection:
        return work(connection)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def dataset_fingerprint(cleaned: Path, batch_size: int, replace_events: bool,
                        purge: bool, mapping_path: Path,
                        version: str = MIGRATION_VERSION) -> str:
    """Everything that can change the result: all CSVs, the mapping file, settings, version."""
    digest = hashlib.sha256()
    for key in FILES:
        digest.update(file_sha256(cleaned / FILES[key]).encode())
    digest.update(file_sha256(Path(mapping_path)).encode())
    digest.update(f"|{batch_size}|{int(replace_events)}|{int(purge)}|{version}".encode())
    return digest.hexdigest()


def check_resume_state(state: dict, fingerprint: str, batch_size: int):
    """Read-only guard: refuse to continue a run started with different inputs."""
    if state["dataset_fingerprint"] != fingerprint or state["batch_size"] != batch_size:
        stop("The data files, user-vendor mapping, batch size, flags or migration version "
             "differ from the run that started this migration. Re-run with the original "
             "inputs, or re-branch to start over. Nothing was changed.")


def describe_db_error(error) -> str:
    """Safe one-line diagnosis: driver class, PostgreSQL code and first message line.

    Never includes the SQL, its parameters, the URL, host, user or password."""
    original = getattr(error, "orig", None) or error
    code = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
    message = (str(original).splitlines() or [""])[0]
    secrets = [os.getenv("DATABASE_URL"), os.getenv("BYTEBITE_MIGRATION_DB_HOST")]
    try:
        from urllib.parse import unquote, urlparse
        parsed = urlparse(os.getenv("DATABASE_URL") or "")
        secrets += [parsed.hostname, parsed.username, parsed.password,
                    unquote(parsed.password or "")]
    except ValueError:
        pass
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        message = message.replace(secret, "<redacted>")
    return (f"{type(original).__name__}, PostgreSQL code {code or 'n/a'}: "
            f"{message[:300] or 'no message'}")


class MigrationSession:
    """The ONE database connection of an apply run; it also holds the advisory lock.

    A session-level PostgreSQL advisory lock lives exactly as long as the
    connection that took it. Every read and write of the run goes through this same
    connection, so the lock cannot be lost independently of the writes: if the
    connection dies, the server rolls back the open transaction and frees the lock
    in one step. No code path opens another connection or reconnects. Before each
    commit the lock is re-verified inside the same transaction.
    """

    def __init__(self, engine):
        self.engine = engine
        self.connection = None
        self.lost = False

    def acquire(self):
        connection = self.engine.connect()
        try:
            got = connection.execute(
                text("SELECT pg_try_advisory_lock(:a, :b)"),
                {"a": LOCK_KEYS[0], "b": LOCK_KEYS[1]}).scalar()
            connection.commit()
        except BaseException:
            self._close(connection)
            raise
        if not got:
            self._close(connection)
            stop("Another migration process is already running against this database. "
                 "Nothing was changed. Wait for it to finish (a crashed run's lock clears "
                 "once the server notices the dropped connection) and try again.")
        self.connection = connection

    @staticmethod
    def _close(connection):
        try:
            connection.close()
        except Exception:
            pass

    def _live(self):
        if self.lost or self.connection is None:
            stop("The migration connection was lost. Nothing was reconnected. Re-run the "
                 "same command: it re-acquires the lock and resumes from the committed ledger.")
        return self.connection

    def _mark_lost(self):
        self.lost = True

    def check(self):
        """Fail unless this very connection still holds the advisory lock."""
        connection = self._live()
        own_transaction = not connection.in_transaction()
        try:
            held = connection.execute(text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted "
                "AND pid = pg_backend_pid() AND classid = :a AND objid = :b"),
                {"a": LOCK_KEYS[0], "b": LOCK_KEYS[1]}).scalar()
        except (OperationalError, InterfaceError):
            self._mark_lost()
            held = 0
        finally:
            if own_transaction and not self.lost:
                try:
                    connection.rollback()
                except Exception:
                    self._mark_lost()
        if not held:
            self._mark_lost()
            stop("The migration lock was lost. Stopping; re-run the same command to resume.")

    @contextmanager
    def _transaction(self, commit: bool):
        connection = self._live()
        if connection.in_transaction():
            stop("Internal error: nested migration transaction.")
        transaction = connection.begin()
        try:
            yield connection
            if commit:
                self.check()          # same connection, same transaction, just before commit
                transaction.commit()
            else:
                transaction.rollback()
        except (OperationalError, InterfaceError) as error:
            self._mark_lost()
            self._rollback(transaction)
            stop("The database connection was lost; the open transaction was not committed. "
                 f"Cause reported by the driver: {describe_db_error(error)}. "
                 "Re-run the same command to resume from the committed ledger.")
        except BaseException:
            self._rollback(transaction)
            raise

    def _rollback(self, transaction):
        try:
            transaction.rollback()
        except Exception:
            self._mark_lost()

    def begin(self):
        """One transaction on the lock connection: commit on success, rollback on error."""
        return self._transaction(commit=True)

    def connect(self):
        """Read-only inspection on the lock connection; always rolled back."""
        return self._transaction(commit=False)

    def release(self):
        connection, self.connection = self.connection, None
        if connection is None:
            return
        try:
            if connection.in_transaction():
                connection.rollback()
            if not self.lost:
                connection.execute(text("SELECT pg_advisory_unlock(:a, :b)"),
                                   {"a": LOCK_KEYS[0], "b": LOCK_KEYS[1]})
                connection.commit()
        except Exception:
            pass  # closing the connection releases the lock anyway
        finally:
            self._close(connection)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def batch_hash(rows) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update("\x1f".join(row).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def iter_batches(path: Path, batch_size: int):
    """Yield (batch_number, rows, hash); file order, batch_size rows each."""
    rows, number = [], 0
    for row in read_rows(path):
        rows.append(row)
        if len(rows) == batch_size:
            yield number, rows, batch_hash(rows)
            rows, number = [], number + 1
    if rows:
        yield number, rows, batch_hash(rows)


def copy_text(connection, sql: str, data: str):
    cursor = connection.connection.cursor()
    try:
        if callable(getattr(cursor, "copy_expert", None)):  # psycopg2
            cursor.copy_expert(sql, io.StringIO(data))
        else:  # psycopg 3
            with cursor.copy(sql) as copy:
                copy.write(data.encode("utf-8"))
    finally:
        cursor.close()


def csv_text(rows) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue()


def read_state(connection):
    if not table_exists(connection, STATE_TABLE):
        return None
    row = connection.execute(text(
        "SELECT status, dataset_fingerprint, batch_size, total_batches, users_before, "
        f"user_digest_before, replace_synthetic_events FROM public.{STATE_TABLE}"
    )).first()
    return dict(row._mapping) if row else None


def set_status(connection, status: str):
    connection.execute(text(
        f"UPDATE public.{STATE_TABLE} SET status = :s, updated_at = now()"
    ), {"s": status})


def committed_batches(connection) -> dict:
    return {n: h for n, h in connection.execute(text(
        f"SELECT batch_no, source_hash FROM public.{BATCH_TABLE}")).all()}


def progress_report(connection):
    state = read_state(connection)
    if not state:
        return None
    return {
        "status": state["status"],
        "batches_committed": connection.execute(text(
            f"SELECT count(*) FROM public.{BATCH_TABLE}")).scalar(),
        "total_batches": state["total_batches"],
        "batch_size": state["batch_size"],
    }


def start_migration(connection, fingerprint, batch_size, total_batches, replace_events):
    """Phase A. Adds columns/tables and opens the migration (app now closed)."""
    require_marker(connection)
    existing = read_state(connection)
    if existing:
        return existing
    for statement in SCHEMA_STATEMENTS:
        connection.execute(text(statement))
    state = {
        "status": CLEARING, "dataset_fingerprint": fingerprint, "batch_size": batch_size,
        "total_batches": total_batches, "users_before": table_count(connection, "users"),
        "user_digest_before": user_digest(connection),
        "replace_synthetic_events": replace_events,
    }
    connection.execute(text(
        f"INSERT INTO public.{STATE_TABLE} (status, dataset_fingerprint, batch_size, "
        "total_batches, users_before, user_digest_before, replace_synthetic_events) "
        "VALUES (:status, :dataset_fingerprint, :batch_size, :total_batches, "
        ":users_before, :user_digest_before, :replace_synthetic_events)"
    ), state)
    return state


def clear_synthetic_data(session, purge: bool, replace_events: bool):
    """Phase B. Committed, idempotent steps; only ever removes non-lecturer rows."""
    def links_and_bound(connection):
        if purge:
            connection.execute(text("DELETE FROM public.notifications"))
            connection.execute(text(
                "DELETE FROM public.report_exports WHERE vendor_id IS NOT NULL"))
        connection.execute(text("DELETE FROM public.user_vendor_links"))
        connection.execute(text(
            "UPDATE public.users SET vendor_id = NULL WHERE vendor_id IS NOT NULL"))

    run_once(session, links_and_bound)

    low, high = run_once(session, lambda c: tuple(c.execute(text(
        "SELECT min(transaction_id), max(transaction_id) FROM public.transactions "
        "WHERE source_uuid IS NULL")).first()))
    if low is not None:
        start, removed = low, 0
        while start <= high:
            end = start + DELETE_CHUNK
            removed += run_once(session, lambda c, a=start, b=end: c.execute(text(
                "DELETE FROM public.transactions WHERE transaction_id >= :a "
                "AND transaction_id < :b AND source_uuid IS NULL"), {"a": a, "b": b}).rowcount)
            print(f"Cleared synthetic transactions: {removed:,}")
            start = end

    def small_tables(connection):
        if connection.execute(text(
                "SELECT count(*) FROM public.transactions WHERE source_uuid IS NOT NULL")).scalar():
            stop("Lecturer transactions exist while clearing; refusing to delete students.")
        connection.execute(text("DELETE FROM public.students"))
        connection.execute(text("DELETE FROM public.vendors WHERE source_uuid IS NULL"))
        connection.execute(text("DELETE FROM public.vendor_types WHERE source_uuid IS NULL"))
        if replace_events:
            connection.execute(text(
                "DELETE FROM public.contextual_events WHERE source = :s AND source_uuid IS NULL"
            ), {"s": SYNTHETIC_EVENT_SOURCE_LABEL})
        set_status(connection, LOADING)

    run_once(session, small_tables)


def load_small_tables(connection, cleaned: Path, mapping: dict):
    """Phase C. Idempotent; also rebuilds the user links from the mapping file."""
    require_marker(connection)
    connection.execute(text(
        "INSERT INTO public.vendor_types (source_uuid, name) VALUES (CAST(:u AS uuid), :n) "
        "ON CONFLICT (source_uuid) DO NOTHING"
    ), [{"u": u, "n": n} for u, n in read_rows(cleaned / FILES["vendor_type"])])
    connection.execute(text(
        "INSERT INTO public.vendors (source_uuid, name, address, gps, type_id) "
        "VALUES (CAST(:u AS uuid), :n, :a, :g, "
        "(SELECT type_id FROM public.vendor_types WHERE source_uuid = CAST(:t AS uuid))) "
        "ON CONFLICT (source_uuid) DO NOTHING"
    ), [
        {"u": r[0], "n": r[1], "a": r[2], "g": gps_wkt(r[3], r[4]), "t": r[5]}
        for r in read_rows(cleaned / FILES["vendor"])
    ])
    connection.execute(text("CREATE TEMP TABLE lecturer_student_stage (id TEXT) ON COMMIT DROP"))
    copy_text(connection, "COPY lecturer_student_stage (id) FROM STDIN WITH (FORMAT csv)",
              csv_text(read_rows(cleaned / FILES["student"])))
    connection.execute(text(
        "INSERT INTO public.students (id_number) SELECT id FROM lecturer_student_stage "
        "ON CONFLICT (id_number) DO NOTHING"))
    now = datetime.now(timezone.utc)
    connection.execute(text(
        "INSERT INTO public.contextual_events "
        "(source_uuid, name, event_type, start_date, end_date, scope, recurring, "
        "source, updated_at) "
        "VALUES (CAST(:u AS uuid), :n, :t, :s, :e, :c, :r, :src, :now) "
        "ON CONFLICT (source_uuid) DO NOTHING"
    ), [
        {"u": r[0], "t": r[1], "n": r[2], "s": date.fromisoformat(r[3]),
         "e": date.fromisoformat(r[4]), "c": r[5], "r": r[6] == "true",
         "src": EVENT_SOURCE_LABEL, "now": now}
        for r in read_rows(cleaned / FILES["calendar_event"])
    ])
    vendor_ids = dict(connection.execute(text(
        "SELECT source_uuid::text, vendor_id FROM public.vendors")).all())
    links = [
        {"u": user_id, "v": vendor_ids[vendor]}
        for user_id, entry in mapping.items() for vendor in entry["vendors"]
    ]
    connection.execute(text("DELETE FROM public.user_vendor_links"))
    connection.execute(text(
        "INSERT INTO public.user_vendor_links (user_id, vendor_id) VALUES (:u, :v)"), links)


def load_batch(connection, number: int, rows: list, source_hash: str, lock=None):
    """One batch: data, exact verification and progress row in ONE transaction."""
    require_marker(connection)
    if connection.execute(text(
            f"SELECT 1 FROM public.{BATCH_TABLE} WHERE batch_no = :n"), {"n": number}).first():
        return "already committed"
    connection.execute(text(
        "CREATE TEMP TABLE lecturer_tx_stage ("
        "row_no BIGINT GENERATED ALWAYS AS IDENTITY, id TEXT, student_id TEXT, "
        "vendor_id TEXT, tx_datetime TEXT, value TEXT, discount TEXT) ON COMMIT DROP"))
    copy_text(connection,
              "COPY lecturer_tx_stage (id, student_id, vendor_id, tx_datetime, value, discount) "
              "FROM STDIN WITH (FORMAT csv)", csv_text(rows))
    connection.execute(text(
        "INSERT INTO public.transactions "
        "(source_uuid, student_id, vendor_id, datetime, value, discount) "
        "SELECT s.id::uuid, s.student_id, v.vendor_id, s.tx_datetime::timestamp, "
        "s.value::numeric, s.discount::numeric "
        "FROM lecturer_tx_stage s JOIN public.vendors v ON v.source_uuid = s.vendor_id::uuid "
        "ORDER BY s.row_no ON CONFLICT (source_uuid) DO NOTHING"))
    exact = connection.execute(text(
        "SELECT count(*) FROM public.transactions t "
        "JOIN lecturer_tx_stage s ON t.source_uuid = s.id::uuid "
        "JOIN public.vendors v ON v.vendor_id = t.vendor_id "
        "WHERE t.value::text = s.value AND t.discount::text = s.discount "
        "AND t.datetime = s.tx_datetime::timestamp AND t.student_id = s.student_id "
        "AND v.source_uuid = s.vendor_id::uuid")).scalar()
    if exact != len(rows):
        stop(f"Batch {number + 1}: only {exact} of {len(rows)} rows match the source; "
             "batch rolled back.")
    if lock:
        lock.check()  # lock lost during a long batch: raise here so nothing commits
    connection.execute(text(
        f"INSERT INTO public.{BATCH_TABLE} (batch_no, row_count, source_hash) "
        "VALUES (:n, :c, :h)"), {"n": number, "c": len(rows), "h": source_hash})
    connection.execute(text(
        f"UPDATE public.{STATE_TABLE} SET updated_at = now()"))
    return "committed"


def load_transactions(session, cleaned: Path, state: dict, max_batches, lock=None):
    """Phase D. Returns True when every batch is committed."""
    done = run_once(session, committed_batches)
    total = state["total_batches"]
    if any(number >= total for number in done):
        stop("Progress table holds batches beyond the file; refusing to continue.")
    new = 0
    for number, rows, digest in iter_batches(cleaned / FILES["transaction"], state["batch_size"]):
        if number in done:
            if done[number] != digest:
                stop(f"Batch {number + 1} was committed from different data; refusing to resume.")
            continue
        if max_batches is not None and new >= max_batches:
            return False
        if lock:
            lock.check()
        run_once(session, lambda c, n=number, r=rows, d=digest: load_batch(c, n, r, d, lock))
        new += 1
        print(f"Batch {number + 1}/{total} committed ({len(rows):,} rows).")
    return True


def finalize(session, cleaned, summary, expected, mapping, state):
    """Phase E. Index, full validation, and only then status 'complete'."""
    run_once(session, lambda c: set_status(c, VALIDATING))
    run_once(session, lambda c: c.execute(text(FINAL_INDEX_STATEMENT)))

    def validate(connection):
        require_marker(connection)
        problems = _mapping_matches_users(connection, mapping)
        if problems:
            stop("User mapping does not match the database:\n  " + "\n  ".join(problems[:30]))
        vendor_ids = dict(connection.execute(text(
            "SELECT source_uuid::text, vendor_id FROM public.vendors")).all())
        verify(connection, cleaned, summary, expected, mapping, vendor_ids, state)
        set_status(connection, COMPLETE)

    run_once(session, validate)


def cmd_apply(args) -> int:
    if not args.replace_synthetic_data:
        stop("Pass --replace-synthetic-data: this deletes the synthetic business rows.")
    if not args.user_vendor_map:
        stop("Pass --user-vendor-map <completed mapping csv>.")
    if args.batch_size < 1000:
        stop("--batch-size must be at least 1000.")
    if args.max_batches is not None and args.max_batches < 1:
        stop("--max-batches must be at least 1.")
    cleaned = Path(args.cleaned_dir)

    # 1. Validate every file offline before any database connection exists.
    summary = validate_sources(cleaned)
    if not summary["ok"]:
        print(json.dumps(public_summary(summary), indent=2))
        stop("CSV validation failed; nothing was changed.")
    mapping = load_user_mapping(Path(args.user_vendor_map), summary["_vendor_ids"])
    expected = summary["transactions"]
    total_batches = -(-summary["files"]["transaction"] // args.batch_size)
    fingerprint = dataset_fingerprint(
        cleaned, args.batch_size, args.replace_synthetic_events,
        args.purge_vendor_bound_records, Path(args.user_vendor_map))

    # 2. Target identity (direct host required), then a human confirmation.
    engine = migration_engine(check_target(args.confirm_target, require_direct=True))
    confirm_interactively("migrate the lecturer data into this database")

    # 3. One migration at a time: the lock is taken before any other database access.
    with MigrationSession(engine) as session:
        return apply_locked(args, session, cleaned, summary, mapping, expected,
                            total_batches, fingerprint)


def apply_locked(args, session, cleaned, summary, mapping, expected,
                 total_batches, fingerprint) -> int:
    # Read-only inspection. The snapshot is written here, before any write.
    with session.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        require_marker(connection)
        for table in LOCKED_TABLES:
            if not table_exists(connection, table):
                stop(f"Table {table} is missing; wrong database?")
        problems = schema_problems(connection)
        if problems:
            stop("Schema check failed:\n  " + "\n  ".join(problems))
        problems = _mapping_matches_users(connection, mapping)
        if problems:
            stop("User mapping does not match the database:\n  " + "\n  ".join(problems[:30]))
        state = read_state(connection)
        if state is None:
            if column_exists(connection, "vendors", "source_uuid") and connection.execute(
                text("SELECT count(*) FROM public.vendors WHERE source_uuid IS NOT NULL")
            ).scalar():
                stop("Lecturer vendors exist but no progress record; refusing to continue.")
            bound = {
                "notifications": table_count(connection, "notifications"),
                "report_exports": connection.execute(text(
                    "SELECT count(*) FROM public.report_exports WHERE vendor_id IS NOT NULL"
                )).scalar(),
            }
            if any(bound.values()) and not args.purge_vendor_bound_records:
                stop("Notifications/report exports refer to synthetic vendor IDs "
                     f"({bound}). Re-run with --purge-vendor-bound-records to delete them.")
            print(f"Pre-migration snapshot written: {snapshot_before_apply(connection).name}")
        else:
            if state["status"] == COMPLETE:
                stop("The migration is already complete.")
            check_resume_state(state, fingerprint, args.batch_size)
            print(f"Resuming: status '{state['status']}'.")

    # Phases. Every step commits on its own and is safe to repeat.
    session.check()
    if state is None:
        state = run_once(session, lambda c: start_migration(
            c, fingerprint, args.batch_size, total_batches, args.replace_synthetic_events))
        print("Migration opened; the app now answers 503 until it completes.")
    if state["status"] == CLEARING:
        clear_synthetic_data(session, args.purge_vendor_bound_records,
                             args.replace_synthetic_events)
    session.check()
    run_once(session, lambda c: load_small_tables(c, cleaned, mapping))
    if not load_transactions(session, cleaned, state, args.max_batches, session):
        print(f"Stopped after {args.max_batches} batch(es) as requested. The app stays "
              "closed. Re-run the same command to continue.")
        return 0
    session.check()
    finalize(session, cleaned, summary, expected, mapping, state)
    print("All validation checks passed; migration marked complete.")

    try:  # statistics only; the migration is already committed
        with session.begin() as connection:
            for table in BUSINESS_TABLES + ["contextual_events"]:
                connection.execute(text(f"ANALYZE public.{table}"))
    except Exception:
        print("Warning: ANALYZE failed; run it manually. The migration itself committed.")
    print("Migration complete.")
    return 0


def verify(connection, cleaned, summary, expected, mapping, vendor_ids, state):
    """Raise (so the 'complete' flag is never set) unless everything matches the source.

    Every transaction row was already compared exactly with its source row inside
    its own batch; the batch ledger below proves every batch was committed.
    """
    checks = []

    def scalar(sql):
        return connection.execute(text(sql)).scalar()

    files = summary["files"]
    checks.append(("vendor_types", table_count(connection, "vendor_types"), files["vendor_type"]))
    checks.append(("vendors", table_count(connection, "vendors"), files["vendor"]))
    checks.append(("students", table_count(connection, "students"), files["student"]))
    checks.append(("transactions", table_count(connection, "transactions"), files["transaction"]))
    checks.append(("batch ledger (batches, rows)", tuple(connection.execute(text(
        f"SELECT count(*), COALESCE(sum(row_count), 0) FROM public.{BATCH_TABLE}")).first()),
        (state["total_batches"], files["transaction"])))
    checks.append(("lecturer events", scalar(
        "SELECT count(*) FROM public.contextual_events WHERE source_uuid IS NOT NULL"),
        files["calendar_event"]))
    if state["replace_synthetic_events"]:
        checks.append(("synthetic events left", scalar(
            "SELECT count(*) FROM public.contextual_events WHERE source_uuid IS NULL "
            f"AND source = '{SYNTHETIC_EVENT_SOURCE_LABEL}'"), 0))
    for table in ("transactions", "vendors", "vendor_types"):
        checks.append((f"{table} missing or duplicate source_uuid", scalar(
            f"SELECT count(*) - count(DISTINCT source_uuid) FROM public.{table}"), 0))
    checks.append(("events duplicate source_uuid", scalar(
        "SELECT count(source_uuid) - count(DISTINCT source_uuid) FROM public.contextual_events"), 0))
    for name, sql, key in (("sum(value)", "SELECT sum(value) FROM public.transactions", "sum_value"),
                           ("sum(discount)", "SELECT sum(discount) FROM public.transactions",
                            "sum_discount")):
        checks.append((name, Decimal(str(scalar(sql))), Decimal(expected[key])))
    checks.append(("earliest", scalar("SELECT min(datetime) FROM public.transactions")
                   .strftime(DATETIME_FORMAT), expected["earliest"]))
    checks.append(("latest", scalar("SELECT max(datetime) FROM public.transactions")
                   .strftime(DATETIME_FORMAT), expected["latest"]))
    checks.append(("orphan transactions", scalar(
        "SELECT count(*) FROM public.transactions t LEFT JOIN public.vendors v "
        "ON v.vendor_id = t.vendor_id LEFT JOIN public.students s ON s.id_number = t.student_id "
        "WHERE v.vendor_id IS NULL OR s.id_number IS NULL"), 0))
    checks.append(("vendor links pointing at missing vendors", scalar(
        "SELECT count(*) FROM public.user_vendor_links l LEFT JOIN public.vendors v "
        "ON v.vendor_id = l.vendor_id WHERE v.vendor_id IS NULL"), 0))
    checks.append(("Staff without exactly one vendor", scalar(
        "SELECT count(*) FROM public.users u WHERE u.role = 'Staff' AND "
        "(SELECT count(*) FROM public.user_vendor_links l WHERE l.user_id = u.user_id) <> 1"), 0))
    checks.append(("Manager without a vendor", scalar(
        "SELECT count(*) FROM public.users u WHERE u.role = 'Manager' AND NOT EXISTS "
        "(SELECT 1 FROM public.user_vendor_links l WHERE l.user_id = u.user_id)"), 0))
    checks.append(("Admins with links", scalar(
        "SELECT count(*) FROM public.user_vendor_links l JOIN public.users u "
        "ON u.user_id = l.user_id WHERE u.role = 'Admin'"), 0))
    checks.append(("user count unchanged", table_count(connection, "users"), state["users_before"]))
    checks.append(("user identities/credentials unchanged", user_digest(connection),
                   state["user_digest_before"]))

    actual_links = {tuple(r) for r in connection.execute(text(
        "SELECT user_id, vendor_id FROM public.user_vendor_links")).all()}
    expected_links = {(u, vendor_ids[v]) for u, m in mapping.items() for v in m["vendors"]}
    checks.append(("user vendor links equal the mapping file", actual_links == expected_links, True))

    types = {r[0]: r[1] for r in read_rows(cleaned / FILES["vendor_type"])}
    got = {r[0]: r[1] for r in connection.execute(text(
        "SELECT source_uuid::text, name FROM public.vendor_types")).all()}
    checks.append(("vendor types identical", got == types, True))

    vendors = {r[0]: (r[1], r[2], gps_wkt(r[3], r[4]), r[5])
               for r in read_rows(cleaned / FILES["vendor"])}
    got = {r[0]: (r[1], r[2], r[3], r[4]) for r in connection.execute(text(
        "SELECT v.source_uuid::text, v.name, v.address, v.gps, t.source_uuid::text "
        "FROM public.vendors v JOIN public.vendor_types t ON t.type_id = v.type_id")).all()}
    checks.append(("vendors identical (name, address, GPS, type)", got == vendors, True))

    events = {r[0]: (r[1], r[2], date.fromisoformat(r[3]), date.fromisoformat(r[4]),
                     r[5], r[6] == "true") for r in read_rows(cleaned / FILES["calendar_event"])}
    got = {r[0]: tuple(r[1:]) for r in connection.execute(text(
        "SELECT source_uuid::text, event_type, name, start_date, end_date, scope, recurring "
        "FROM public.contextual_events WHERE source_uuid IS NOT NULL")).all()}
    checks.append(("events identical (type, name, dates, scope, recurring)", got == events, True))

    source_students = sorted(r[0] for r in read_rows(cleaned / FILES["student"]))
    digest = hashlib.md5(",".join(source_students).encode("utf-8")).hexdigest()
    checks.append(("student ID set identical", scalar(
        "SELECT md5(string_agg(id_number, ',' ORDER BY id_number COLLATE \"C\")) "
        "FROM public.students"), digest))

    failures = [f"{name}: got {got!r}, expected {want!r}"
                for name, got, want in checks if got != want]
    if failures:
        stop("Post-load checks failed; the migration was NOT marked complete:\n  "
             + "\n  ".join(failures))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, db=True):
        p.add_argument("--cleaned-dir", default=str(CLEANED_DIR))
        if db:
            p.add_argument("--confirm-target", default="")

    p = sub.add_parser("preflight")
    common(p)
    p.add_argument("--user-vendor-map")
    p.add_argument("--check-db", action="store_true",
                   help="Also run read-only database checks (needs the safety env vars).")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("write-user-mapping-template")
    common(p)
    p.add_argument("--overwrite-template", action="store_true")
    p.set_defaults(func=cmd_write_template)

    p = sub.add_parser("init-marker")
    common(p)
    p.set_defaults(func=cmd_init_marker)

    p = sub.add_parser("apply")
    common(p)
    p.add_argument("--user-vendor-map")
    p.add_argument("--replace-synthetic-data", action="store_true")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--max-batches", type=int, default=None,
                   help="Stop after this many new batches (test run).")
    p.add_argument("--replace-synthetic-events", action="store_true",
                   help="Also delete the synthetic contextual_events (recommended).")
    p.add_argument("--purge-vendor-bound-records", action="store_true",
                   help="Delete notifications and vendor report exports that point at synthetic vendors.")
    p.set_defaults(func=cmd_apply)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MigrationError as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # never echo SQL parameters, URLs or hosts
        message = (str(getattr(error, "orig", None) or error).splitlines() or [""])[0]
        secrets = [os.getenv("DATABASE_URL"), os.getenv("BYTEBITE_MIGRATION_DB_HOST")]
        try:
            from urllib.parse import urlparse
            secrets.append(urlparse(os.getenv("DATABASE_URL") or "").hostname)
        except ValueError:
            pass
        for secret in filter(None, secrets):
            message = message.replace(secret, "<redacted>")
        print(f"Migration failed and was rolled back: {type(error).__name__}: {message}",
              file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
