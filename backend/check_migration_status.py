"""Read-only migration status probe used by run_remaining_migration.bat.

Writes "<status> <batches_committed>" to the file given as argv[1] and exits with:
  0  status is loading or validating (safe to continue)
  10 status is complete
  20 no migration state exists (never start one from the batch file)
  21 target safety check refused
  22 any other error (unreadable ledger, connection problem, unexpected status)
It only runs SELECTs inside a READ ONLY transaction that is rolled back.
"""
import sys

import migrate_lecturer_data as m
from sqlalchemy import text


def main() -> int:
    out = sys.argv[1]
    try:
        engine = m.check_target(m.TARGET_NAME, require_direct=True)
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            m.require_marker(connection)
            progress = m.progress_report(connection)
            connection.rollback()
    except m.MigrationError as error:
        print(f"Status check refused: {error}", file=sys.stderr)
        return 21
    except Exception as error:
        print(f"Status check failed: {m.describe_db_error(error)}", file=sys.stderr)
        return 22
    if progress is None:
        print("No migration state exists on this database.")
        return 20
    print(f"status={progress['status']} batches={progress['batches_committed']}"
          f"/{progress['total_batches']} batch_size={progress['batch_size']}")
    with open(out, "w", encoding="ascii") as handle:
        handle.write(f"{progress['status']} {progress['batches_committed']}\n")
    if progress["status"] == m.COMPLETE:
        return 10
    if progress["status"] in (m.LOADING, m.VALIDATING):
        return 0
    print(f"Status '{progress['status']}' must be resumed by hand, not by this loop.",
          file=sys.stderr)
    return 22


if __name__ == "__main__":
    sys.exit(main())
