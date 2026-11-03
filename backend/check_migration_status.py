# Read-only migration status 
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
