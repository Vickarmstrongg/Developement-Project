"""Review-only migration proposal for the synthetic-data-dev Neon branch.

This script is intentionally inert unless all of the following are supplied:
--apply, --confirm-target synthetic-data-dev, BYTEBITE_TARGET_BRANCH,
BYTEBITE_DEV_DB_HOST, and BYTEBITE_DEV_DB_NAME.

It only adds the missing supporting schema. It never drops or alters the four
original business tables or the legacy context_events table.

Open BRD decision: users.vendor_id currently has an FK to vendors, although
BRD v2 says supporting vendor references should not FK into the original
tables. This migration preserves that legacy column/FK for application
compatibility. Decide separately whether a future migration should retire it.
"""

import argparse
import os

from sqlalchemy import text

import database


EXPECTED_BRANCH = "synthetic-data-dev"
ORIGINAL_TABLES = {
    "students": {"id_number"},
    "vendors": {"vendor_id", "type_id"},
    "vendor_types": {"type_id"},
    "transactions": {"transaction_id", "student_id", "vendor_id"},
}
USER_COLUMNS = {
    "full_name": "VARCHAR",
    "status": "VARCHAR",
    "token_hash": "VARCHAR",
    "token_expires_at": "TIMESTAMPTZ",
    "failed_login_attempts": "INTEGER NOT NULL DEFAULT 0",
    "locked": "BOOLEAN NOT NULL DEFAULT FALSE",
}
SUPPORTING_TABLES = {
    "user_vendor_links",
    "notifications",
    "report_exports",
    "contextual_events",
}


def stop(message: str) -> None:
    raise RuntimeError(f"Migration stopped: {message}")


def check_target(confirm_target: str) -> None:
    if confirm_target != EXPECTED_BRANCH:
        stop(f"Pass --confirm-target {EXPECTED_BRANCH} to continue.")
    if os.getenv("BYTEBITE_TARGET_BRANCH") != EXPECTED_BRANCH:
        stop(f"BYTEBITE_TARGET_BRANCH must be {EXPECTED_BRANCH}.")

    expected_host = os.getenv("BYTEBITE_DEV_DB_HOST")
    expected_database = os.getenv("BYTEBITE_DEV_DB_NAME")
    if not expected_host or not expected_database:
        stop("Set BYTEBITE_DEV_DB_HOST and BYTEBITE_DEV_DB_NAME first.")

    actual_host = database.engine.url.host
    if not actual_host or actual_host != expected_host:
        stop("DATABASE_URL host does not match BYTEBITE_DEV_DB_HOST.")
    if database.engine.url.database != expected_database:
        stop("DATABASE_URL database does not match BYTEBITE_DEV_DB_NAME.")


def table_columns(connection, table_name: str) -> set[str]:
    return set(connection.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = :table_name
    """), {"table_name": table_name}).scalars())


def verify_original_schema(connection) -> None:
    schema_name = connection.execute(text("SELECT current_schema()")).scalar_one()
    if schema_name != "public":
        stop("The connected session must use the public schema.")

    for table_name, required_columns in ORIGINAL_TABLES.items():
        actual = table_columns(connection, table_name)
        missing = required_columns - actual
        if missing:
            stop(
                f"Original table {table_name} is missing required columns: "
                + ", ".join(sorted(missing))
            )

    expected_constraints = {
        ("students", "p", "id_number", None, None),
        ("vendors", "p", "vendor_id", None, None),
        ("vendor_types", "p", "type_id", None, None),
        ("transactions", "p", "transaction_id", None, None),
        ("transactions", "f", "student_id", "students", "id_number"),
        ("transactions", "f", "vendor_id", "vendors", "vendor_id"),
        ("vendors", "f", "type_id", "vendor_types", "type_id"),
    }
    actual_constraints = {
        tuple(row) for row in connection.execute(text("""
        SELECT source.relname,
               constraint_row.contype::text,
               source_column.attname,
               target.relname,
               target_column.attname
        FROM pg_catalog.pg_constraint AS constraint_row
        JOIN pg_catalog.pg_class AS source
          ON source.oid = constraint_row.conrelid
        JOIN pg_catalog.pg_namespace AS source_schema
          ON source_schema.oid = source.relnamespace
        JOIN pg_catalog.pg_attribute AS source_column
          ON source_column.attrelid = source.oid
         AND source_column.attnum = constraint_row.conkey[1]
        LEFT JOIN pg_catalog.pg_class AS target
          ON target.oid = constraint_row.confrelid
        LEFT JOIN pg_catalog.pg_attribute AS target_column
          ON target_column.attrelid = target.oid
         AND target_column.attnum = constraint_row.confkey[1]
        WHERE source_schema.nspname = current_schema()
          AND source.relname = ANY(:tables)
          AND constraint_row.contype IN ('p', 'f')
          AND cardinality(constraint_row.conkey) = 1
          AND constraint_row.convalidated
    """), {"tables": list(ORIGINAL_TABLES)}).all()
    }
    missing_constraints = expected_constraints - actual_constraints
    if missing_constraints:
        stop("Required original-table primary/foreign keys are missing.")


def verify_created_schema(connection) -> None:
    tables = set(connection.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
    """)).scalars())
    missing_tables = SUPPORTING_TABLES - tables
    if missing_tables:
        stop("Supporting tables were not created: " + ", ".join(sorted(missing_tables)))

    for column_name in USER_COLUMNS:
        if column_name not in table_columns(connection, "users"):
            stop(f"users.{column_name} was not created.")

    user_column_details = {
        row["column_name"]: row
        for row in connection.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'users'
              AND column_name = ANY(:columns)
        """), {"columns": list(USER_COLUMNS)}).mappings()
    }
    expected_user_types = {
        "full_name": ("character varying", "YES"),
        "status": ("character varying", "YES"),
        "token_hash": ("character varying", "YES"),
        "token_expires_at": ("timestamp with time zone", "YES"),
        "failed_login_attempts": ("integer", "NO"),
        "locked": ("boolean", "NO"),
    }
    for column_name, (expected_type, expected_nullable) in expected_user_types.items():
        actual = user_column_details[column_name]
        if actual["data_type"] != expected_type or actual["is_nullable"] != expected_nullable:
            stop(f"users.{column_name} does not match the expected type/nullability.")
        if column_name in {"failed_login_attempts", "locked"} and actual["column_default"] is None:
            stop(f"users.{column_name} is missing its safe default.")
    required_columns = {
        "user_vendor_links": {"user_id", "vendor_id"},
        "notifications": {
            "notification_id", "user_id", "vendor_id", "message",
            "trigger_type", "is_read", "is_pinned", "is_cleared", "created_at",
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
    for table_name, expected in required_columns.items():
        missing = expected - table_columns(connection, table_name)
        if missing:
            stop(
                f"{table_name} is incomplete; missing: "
                + ", ".join(sorted(missing))
            )

    required_constraints = {
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
    for table_name, expected_definitions in required_constraints.items():
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
        missing = [
            definition for definition in expected_definitions
            if " ".join(definition.upper().split()) not in definitions
        ]
        if missing:
            stop(f"{table_name} is missing one or more required key constraints.")


def migrate(connection) -> None:
    verify_original_schema(connection)

    for column_name, definition in USER_COLUMNS.items():
        connection.execute(text(
            f"ALTER TABLE public.users ADD COLUMN IF NOT EXISTS "
            f"{column_name} {definition}"
        ))

    statements = (
        """
        CREATE TABLE IF NOT EXISTS public.user_vendor_links (
            user_id INTEGER NOT NULL,
            vendor_id INTEGER NOT NULL,
            CONSTRAINT user_vendor_links_pkey PRIMARY KEY (user_id, vendor_id),
            CONSTRAINT user_vendor_links_user_fk
                FOREIGN KEY (user_id) REFERENCES public.users(user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS public.notifications (
            notification_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id INTEGER NOT NULL,
            vendor_id INTEGER NOT NULL,
            message TEXT,
            trigger_type VARCHAR,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
            is_cleared BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT notifications_user_fk
                FOREIGN KEY (user_id) REFERENCES public.users(user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS public.report_exports (
            report_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            vendor_id INTEGER,
            generated_by_user_id INTEGER,
            report_type VARCHAR,
            period_start DATE,
            period_end DATE,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT report_exports_user_fk
                FOREIGN KEY (generated_by_user_id) REFERENCES public.users(user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS public.contextual_events (
            event_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            source_context_id TEXT UNIQUE,
            source_year SMALLINT,
            name TEXT NOT NULL,
            event_type VARCHAR NOT NULL,
            subcategory TEXT,
            start_date DATE NOT NULL,
            start_time TIME,
            end_date DATE NOT NULL,
            end_time TIME,
            all_day BOOLEAN,
            location TEXT,
            campus TEXT,
            faculty TEXT,
            scope TEXT,
            source VARCHAR NOT NULL,
            source_organisation TEXT,
            source_name TEXT,
            source_file TEXT,
            source_url TEXT,
            source_page TEXT,
            verification_status TEXT,
            notes TEXT,
            created_by_user_id INTEGER,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT contextual_events_user_fk
                FOREIGN KEY (created_by_user_id) REFERENCES public.users(user_id)
        )
        """,
    )
    for statement in statements:
        connection.execute(text(statement))

    verify_created_schema(connection)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the proposed migration.")
    parser.add_argument("--confirm-target", default="", help="Must be synthetic-data-dev.")
    args = parser.parse_args()

    if not args.apply:
        print("Plan only. No connection or database changes were made.")
        print("Supporting tables: " + ", ".join(sorted(SUPPORTING_TABLES)))
        print("Add users columns: " + ", ".join(USER_COLUMNS))
        return

    check_target(args.confirm_target)
    with database.engine.begin() as connection:
        database_name = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()
        expected_database = os.environ["BYTEBITE_DEV_DB_NAME"]
        if database_name != expected_database:
            stop("Connected database name does not match BYTEBITE_DEV_DB_NAME.")
        migrate(connection)

    print("Migration completed; original business and context_events tables were not altered.")


if __name__ == "__main__":
    main()
