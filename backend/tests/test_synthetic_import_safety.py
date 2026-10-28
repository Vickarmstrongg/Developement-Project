"""Local-only tests for the proposed synthetic-data scripts.

These tests replace the ``database`` and ``models`` modules before loading any
draft script. No backend database configuration, .env file, engine, or database
connection is imported or used.
"""

import csv
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


BACKEND = Path(__file__).resolve().parents[1]
EVENT_HEADERS = (
    "context_id", "year", "category", "subcategory", "title", "start_date",
    "start_time", "end_date", "end_time", "all_day", "location", "campus",
    "faculty", "scope", "source_organisation", "source_name", "source_file",
    "source_url", "source_page", "verification_status", "notes",
)
DATA_HEADERS = {
    "Student.csv": (
        "id_number", "last_name", "first_name", "dob", "gender",
        "email", "phone", "address",
    ),
    "Vendor_Type.csv": ("type_id", "name"),
    "Vendor.csv": ("vendor_id", "name", "address", "gps", "type_id"),
    "Transaction.csv": (
        "transaction_id", "student_id", "vendor_id", "datetime", "value", "discount",
    ),
}


def _load_draft_module(filename: str, database_stub, models_stub):
    module_name = Path(filename).stem
    spec = importlib.util.spec_from_file_location(
        module_name,
        BACKEND / filename,
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"database": database_stub, "models": models_stub}):
        spec.loader.exec_module(module)
    return module


def setUpModule():
    sys.path.insert(0, str(BACKEND))
    database_stub = ModuleType("database")
    database_stub.engine = SimpleNamespace(
        url=SimpleNamespace(host="expected.test", database="test_db"),
        connect=Mock(side_effect=AssertionError("Database connection is forbidden in these tests.")),
        begin=Mock(side_effect=AssertionError("Database writes are forbidden in these tests.")),
    )
    database_stub.get_db = Mock(
        side_effect=AssertionError("Database sessions are forbidden in these tests.")
    )
    models_stub = ModuleType("models")
    models_stub.ContextualEvent = SimpleNamespace(__table__=None)
    security_stub = ModuleType("access.security")
    security_stub.hash_password = Mock(return_value="test-hash")
    global migration, importer, validator, seed_admin, isolated_database
    isolated_database = database_stub
    migration = _load_draft_module("proposed_schema_migration.py", database_stub, models_stub)
    importer = _load_draft_module("import_synthetic_data.py", database_stub, models_stub)
    validator = _load_draft_module("validate_synthetic_import.py", database_stub, models_stub)
    seed_spec = importlib.util.spec_from_file_location(
        "access.seed_admin",
        BACKEND / "access" / "seed_admin.py",
    )
    seed_admin = importlib.util.module_from_spec(seed_spec)
    with patch.dict(sys.modules, {
        "database": database_stub,
        "models": models_stub,
        "access.security": security_stub,
    }):
        sys.modules["access.seed_admin"] = seed_admin
        seed_spec.loader.exec_module(seed_admin)


def tearDownModule():
    if str(BACKEND) in sys.path:
        sys.path.remove(str(BACKEND))


def write_csv(path: Path, headers, rows, *, bom=False):
    encoding = "utf-8-sig" if bom else "utf-8"
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def student_row(**overrides):
    row = {
        "id_number": "source-student-1",
        "last_name": "Synthetic",
        "first_name": "Student",
        "dob": "2000-01-02",
        "gender": "X",
        "email": "student@example.invalid",
        "phone": "0000000000",
        "address": "Not imported",
    }
    row.update(overrides)
    return row


def event_row(context_id, year):
    return {
        "context_id": context_id,
        "year": str(year),
        "category": "University",
        "subcategory": "",
        "title": "Fixture event",
        "start_date": f"{year}-01-02",
        "start_time": "",
        "end_date": f"{year}-01-02",
        "end_time": "",
        "all_day": "true",
        "location": "",
        "campus": "",
        "faculty": "",
        "scope": "",
        "source_organisation": "",
        "source_name": "",
        "source_file": "",
        "source_url": "",
        "source_page": "",
        "verification_status": "verified",
        "notes": "",
    }


class DraftImportSafetyTests(unittest.TestCase):
    def _make_sources(
        self,
        root: Path,
        *,
        students=None,
        vendor_types=None,
        vendors=None,
        transactions=None,
        events_by_year=None,
    ):
        data_dir = root / "data"
        context_dir = root / "context"
        data_dir.mkdir(exist_ok=True)
        context_dir.mkdir(exist_ok=True)
        students = students if students is not None else [student_row()]
        vendor_types = vendor_types if vendor_types is not None else [
            {"type_id": "1", "name": "Cafe"},
        ]
        vendors = vendors if vendors is not None else [{
            "vendor_id": "10",
            "name": "Synthetic Vendor",
            "address": "Fixture address",
            "gps": "POINT(18.86 -33.93)",
            "type_id": "1",
        }]
        transactions = transactions if transactions is not None else [{
            "transaction_id": "100",
            "student_id": "source-student-1",
            "vendor_id": "10",
            "datetime": "2025-01-02 08:30:00",
            "value": "12.34",
            "discount": "1.20",
        }]
        rows_by_name = {
            "Student.csv": students,
            "Vendor_Type.csv": vendor_types,
            "Vendor.csv": vendors,
            "Transaction.csv": transactions,
        }
        for name, rows in rows_by_name.items():
            write_csv(data_dir / name, DATA_HEADERS[name], rows, bom=(name == "Student.csv"))

        if events_by_year is None:
            events_by_year = {
                year: [event_row(f"event-{year}", year)]
                for year in (2023, 2024, 2025)
            }
        for year in (2023, 2024, 2025):
            write_csv(
                context_dir / f"context_events_{year}.csv",
                EVENT_HEADERS,
                events_by_year.get(year, []),
            )
        expected_counts = {
            "Student.csv": len(students),
            "Vendor_Type.csv": len(vendor_types),
            "Vendor.csv": len(vendors),
            "Transaction.csv": len(transactions),
            **{
                f"context_events_{year}.csv": len(events_by_year.get(year, []))
                for year in (2023, 2024, 2025)
            },
        }
        return data_dir, context_dir, expected_counts

    def _validate_sources(self, root: Path, **source_options):
        data_dir, context_dir, counts = self._make_sources(root, **source_options)
        with (
            patch.object(importer, "DATA_DIRECTORY", data_dir),
            patch.object(importer, "CONTEXT_DIRECTORY", context_dir),
            patch.object(importer, "SOURCE_COUNTS", counts),
        ):
            return importer.validate_sources(b"local-test-key" * 3)

    def test_utf8_bom_headers_are_read(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Student.csv"
            write_csv(
                path,
                DATA_HEADERS["Student.csv"],
                [student_row(id_number="fixture-student-id")],
                bom=True,
            )
            source, reader = importer.read_csv(path, set(DATA_HEADERS["Student.csv"]))
            try:
                self.assertIn("id_number", reader.fieldnames)
                self.assertTrue(next(reader)["id_number"] == "fixture-student-id")
            finally:
                source.close()

    def test_missing_and_incorrect_headers_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.csv"
            write_csv(path, ("id_number", "dob"), [])
            with self.assertRaisesRegex(ValueError, "headers differ"):
                importer.read_csv(path, {"id_number", "dob", "email"})

            write_csv(path, ("wrong", "headers"), [])
            with self.assertRaisesRegex(ValueError, "headers differ"):
                importer.read_csv(path, {"id_number", "dob"})

    def test_hmac_pseudonym_is_stable_and_keyed(self):
        pseudonym = importer.pseudonym
        self.assertEqual(pseudonym("student-1", b"key-a"), pseudonym("student-1", b"key-a"))
        self.assertNotEqual(pseudonym("student-1", b"key-a"), pseudonym("student-1", b"key-b"))
        self.assertNotEqual(pseudonym("student-1", b"key-a"), pseudonym("student-2", b"key-a"))

    def test_decimal_parser_preserves_valid_decimal_value(self):
        self.assertEqual(
            importer.parse_decimal("1234.5600", "value").as_tuple(),
            importer.Decimal("1234.5600").as_tuple(),
        )
        with self.assertRaises(ValueError):
            importer.parse_decimal("not-a-number", "value")

    def test_source_fingerprint_detects_changed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir, context_dir, _ = self._make_sources(root)
            with (
                patch.object(importer, "DATA_DIRECTORY", data_dir),
                patch.object(importer, "CONTEXT_DIRECTORY", context_dir),
            ):
                fingerprint = importer.fingerprint_source_files()
                with (data_dir / "Student.csv").open("a", encoding="utf-8") as stream:
                    stream.write("\n")
                with self.assertRaisesRegex(RuntimeError, "source CSV changed"):
                    importer.verify_source_fingerprints(fingerprint)

    def test_psycopg3_copy_stream_pseudonymizes_and_reports_progress(self):
        rows = [
            {
                "transaction_id": str(index),
                "student_id": f"fixture-student-{index}",
                "vendor_id": "10",
                "datetime": "2025-01-02 08:30:00",
                "value": "12.3400",
                "discount": "1.20",
            }
            for index in range(1, 4)
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "transactions.csv"
            write_csv(path, DATA_HEADERS["Transaction.csv"], rows)
            written = []
            progress = []

            class CopyContext:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback):
                    return False

                def write_row(self, values):
                    written.append(values)

            class Psycopg3Cursor:
                def copy(self, statement):
                    self.statement = statement
                    return CopyContext()

                def close(self):
                    self.closed = True

            cursor = Psycopg3Cursor()
            driver = SimpleNamespace(cursor=lambda: cursor)
            connection = SimpleNamespace(
                connection=SimpleNamespace(driver_connection=driver),
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                count = importer.bulk_copy_transactions(
                    connection,
                    path,
                    b"local-test-hmac-key",
                    expected_count=3,
                    progress_interval=2,
                    progress_callback=lambda count, elapsed: progress.append(
                        (count, elapsed)
                    ),
                )

        self.assertEqual(count, 3)
        self.assertEqual([row[0] for row in written], [1, 2, 3])
        self.assertEqual(
            written[0][1],
            importer.pseudonym("fixture-student-1", b"local-test-hmac-key"),
        )
        self.assertEqual(written[0][4], importer.Decimal("12.3400"))
        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0][0], 2)
        self.assertGreaterEqual(progress[0][1], 0)
        self.assertIn("Transaction COPY complete: 3 rows", output.getvalue())
        self.assertTrue(cursor.closed)

    def test_psycopg3_copy_error_propagates_and_closes_cursor(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "transactions.csv"
            write_csv(
                path,
                DATA_HEADERS["Transaction.csv"],
                [{
                    "transaction_id": "1",
                    "student_id": "fixture-student",
                    "vendor_id": "10",
                    "datetime": "2025-01-02 08:30:00",
                    "value": "1.00",
                    "discount": "0.00",
                }],
            )

            class CopyContext:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback):
                    return False

                def write_row(self, values):
                    raise RuntimeError("simulated COPY failure")

            class Psycopg3Cursor:
                def copy(self, statement):
                    return CopyContext()

                def close(self):
                    self.closed = True

            cursor = Psycopg3Cursor()
            connection = SimpleNamespace(
                connection=SimpleNamespace(
                    driver_connection=SimpleNamespace(cursor=lambda: cursor),
                ),
            )
            with self.assertRaisesRegex(RuntimeError, "simulated COPY failure"):
                importer.bulk_copy_transactions(
                    connection, path, b"local-test-key", expected_count=1,
                )
        self.assertTrue(cursor.closed)

    def test_psycopg2_copy_fallback_uses_and_closes_temporary_stream(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "transactions.csv"
            write_csv(
                path,
                DATA_HEADERS["Transaction.csv"],
                [{
                    "transaction_id": "1",
                    "student_id": "fixture-student",
                    "vendor_id": "10",
                    "datetime": "2025-01-02 08:30:00",
                    "value": "1.00",
                    "discount": "0.00",
                }],
            )

            class Psycopg2Cursor:
                def copy_expert(self, statement, stream):
                    self.statement = statement
                    self.stream = stream
                    self.payload = stream.read()

                def close(self):
                    self.closed = True

            cursor = Psycopg2Cursor()
            connection = SimpleNamespace(
                connection=SimpleNamespace(
                    driver_connection=SimpleNamespace(cursor=lambda: cursor),
                ),
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                count = importer.bulk_copy_transactions(
                    connection, path, b"local-test-key", expected_count=1,
                )

        self.assertEqual(count, 1)
        self.assertIn(importer.pseudonym("fixture-student", b"local-test-key"), cursor.payload)
        self.assertIn("COPY public.transactions", cursor.statement)
        self.assertTrue(cursor.closed)
        self.assertTrue(cursor.stream.closed)
        self.assertIn("Transaction COPY complete: 1 rows", output.getvalue())

    def test_duplicate_student_ids_are_rejected(self):
        duplicate_rows = [student_row(), student_row()]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(importer.SourceValidationError) as error:
                self._validate_sources(
                    Path(temp),
                    students=duplicate_rows,
                )
        self.assertTrue(any("duplicate student key" in reason for reason in error.exception.issues))

    def test_duplicate_transaction_ids_are_rejected(self):
        transactions = [
            {
                "transaction_id": "100",
                "student_id": "source-student-1",
                "vendor_id": "10",
                "datetime": "2025-01-02 08:30:00",
                "value": "12.34",
                "discount": "1.20",
            },
            {
                "transaction_id": "100",
                "student_id": "source-student-1",
                "vendor_id": "10",
                "datetime": "2025-01-03 08:30:00",
                "value": "15.00",
                "discount": "0",
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(importer.SourceValidationError) as error:
                self._validate_sources(Path(temp), transactions=transactions)
        self.assertTrue(any("duplicate transaction key" in reason for reason in error.exception.issues))

    def test_missing_student_or_vendor_references_are_rejected(self):
        transactions = [{
            "transaction_id": "100",
            "student_id": "source-student-1",
            "vendor_id": "999",
            "datetime": "2025-01-02 08:30:00",
            "value": "12.34",
            "discount": "1.20",
        }]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(importer.SourceValidationError) as error:
                self._validate_sources(Path(temp), transactions=transactions)
        reasons = " ".join(error.exception.issues)
        self.assertIn("unknown vendor reference", reasons)
        self.assertNotIn("unknown student reference", reasons)

    def test_malformed_student_date_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(importer.SourceValidationError) as error:
                self._validate_sources(
                    Path(temp),
                    students=[student_row(dob="not-a-date")],
                )
        self.assertTrue(any("dob must be YYYY-MM-DD" in reason for reason in error.exception.issues))

    def test_negative_value_and_discount_are_rejected_independently(self):
        for field in ("value", "discount"):
            transaction = {
                "transaction_id": "100",
                "student_id": "source-student-1",
                "vendor_id": "10",
                "datetime": "2025-01-02 08:30:00",
                "value": "12.34",
                "discount": "1.20",
            }
            transaction[field] = "-0.01"
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(importer.SourceValidationError) as error:
                    self._validate_sources(Path(temp), transactions=[transaction])
                self.assertTrue(any("must not be negative" in reason for reason in error.exception.issues))

    def test_valid_small_dataset_passes_source_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            validated = self._validate_sources(Path(temp))
        self.assertEqual(validated["transaction_count"], 1)
        self.assertEqual(len(validated["students"]), 1)
        self.assertEqual(len(validated["events"]), 3)
        imported_student = validated["students"][0]
        self.assertTrue(imported_student["id_number"].startswith("dev_"))
        for personal_field in ("last_name", "first_name", "email", "phone", "address"):
            self.assertIsNone(imported_student[personal_field])

    def test_legacy_context_fingerprint_changes_without_emitting_rows(self):
        class FakeResult:
            def __init__(self, rows):
                self.rows = rows

            def mappings(self):
                return iter(self.rows)

        class FakeConnection:
            def __init__(self, rows):
                self.rows = rows

            def execute(self, statement):
                self.statement = str(statement)
                return FakeResult(self.rows)

        original = [{
            "context_id": "fixture-event",
            "category": "University",
            "subcategory": None,
            "title": "Fixture",
            "start_date": "2025-01-01",
            "end_date": "2025-01-01",
            "notes": None,
        }]
        changed = [dict(original[0], title="Changed fixture")]
        first = importer.legacy_context_fingerprint(FakeConnection(original))
        identical = importer.legacy_context_fingerprint(FakeConnection(original))
        different = importer.legacy_context_fingerprint(FakeConnection(changed))
        self.assertEqual(first, identical)
        self.assertEqual(first[0], 1)
        self.assertNotEqual(first[1], different[1])

    def test_event_source_ids_match_and_missing_ids_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            events_by_year = {
                year: [
                    event_row(f"fixture-{year}-{index}", year)
                    for index in range(count)
                ]
                for year, count in ((2023, 67), (2024, 59), (2025, 65))
            }
            _, context_dir, _ = self._make_sources(
                Path(temp),
                events_by_year=events_by_year,
            )
            files = tuple(
                context_dir / f"context_events_{year}.csv"
                for year in (2023, 2024, 2025)
            )
            with patch.object(validator, "CONTEXT_FILES", files):
                parsed = validator.source_event_rows()
                self.assertEqual(len(parsed), 191)

            events_by_year[2024].pop()
            write_csv(
                context_dir / "context_events_2024.csv",
                EVENT_HEADERS,
                events_by_year[2024],
            )
            with patch.object(validator, "CONTEXT_FILES", files):
                with self.assertRaisesRegex(ValueError, "reviewed record count"):
                    validator.source_event_rows()

    def test_duplicate_event_source_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            _, context_dir, _ = self._make_sources(Path(temp))
            duplicate = event_row("event-2023", 2024)
            write_csv(context_dir / "context_events_2024.csv", EVENT_HEADERS, [duplicate])
            files = tuple(
                context_dir / f"context_events_{year}.csv"
                for year in (2023, 2024, 2025)
            )
            with (
                patch.object(validator, "CONTEXT_FILES", files),
                patch.object(validator, "CONTEXT_COUNTS", {2023: 1, 2024: 1, 2025: 1}),
                self.assertRaisesRegex(ValueError, "duplicate event key"),
            ):
                validator.source_event_rows()

    def test_importer_and_migration_target_guards_fail_without_connecting(self):
        env = {
            "BYTEBITE_TARGET_BRANCH": "synthetic-data-dev",
            "BYTEBITE_DEV_DB_HOST": "expected.test",
            "BYTEBITE_DEV_DB_NAME": "test_db",
            "BYTEBITE_STUDENT_ID_HMAC_KEY": "x" * 32,
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.object(importer.database.engine.url, "host", "different.test"):
                with self.assertRaisesRegex(RuntimeError, "host does not match"):
                    importer.check_target("synthetic-data-dev")
                with self.assertRaisesRegex(RuntimeError, "host does not match"):
                    migration.check_target("synthetic-data-dev")
            with self.assertRaisesRegex(RuntimeError, "Pass --confirm-target"):
                importer.check_target("wrong-branch")
            with patch.dict(os.environ, {"BYTEBITE_TARGET_BRANCH": "wrong-branch"}):
                with self.assertRaisesRegex(RuntimeError, "BYTEBITE_TARGET_BRANCH"):
                    migration.check_target("synthetic-data-dev")
            with patch.dict(os.environ, {"BYTEBITE_DEV_DB_NAME": "wrong_db"}):
                with self.assertRaisesRegex(RuntimeError, "database"):
                    importer.check_target("synthetic-data-dev")
        self.assertEqual(isolated_database.engine.connect.call_count, 0)

    def test_command_entrypoints_fail_target_guard_before_begin(self):
        env = {
            "BYTEBITE_TARGET_BRANCH": "synthetic-data-dev",
            "BYTEBITE_DEV_DB_HOST": "expected.test",
            "BYTEBITE_DEV_DB_NAME": "test_db",
            "BYTEBITE_STUDENT_ID_HMAC_KEY": "x" * 32,
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(importer.database.engine.url, "host", "different.test"),
            patch.object(importer.database.engine, "begin") as begin_mock,
            patch.object(
                sys,
                "argv",
                [
                    "import_synthetic_data.py",
                    "--replace-business-data",
                    "--confirm-target",
                    "synthetic-data-dev",
                ],
            ),
            self.assertRaisesRegex(RuntimeError, "host does not match"),
        ):
            importer.main()
        begin_mock.assert_not_called()
        self.assertEqual(isolated_database.engine.connect.call_count, 0)

        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(migration.database.engine.url, "host", "different.test"),
            patch.object(migration.database.engine, "begin") as migration_begin,
            patch.object(
                sys,
                "argv",
                [
                    "proposed_schema_migration.py",
                    "--apply",
                    "--confirm-target",
                    "synthetic-data-dev",
                ],
            ),
            self.assertRaisesRegex(RuntimeError, "host does not match"),
        ):
            migration.main()
        migration_begin.assert_not_called()
        self.assertEqual(isolated_database.engine.connect.call_count, 0)

    def test_all_target_guards_reject_missing_configuration_without_connecting(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                importer.check_target("synthetic-data-dev")
            with self.assertRaises(RuntimeError):
                migration.check_target("synthetic-data-dev")
            with self.assertRaises(RuntimeError):
                validator.require_target()
        self.assertEqual(isolated_database.engine.connect.call_count, 0)
        self.assertEqual(isolated_database.engine.begin.call_count, 0)

    def test_importer_database_error_uses_transaction_rollback_path(self):
        class FakeConnection:
            def execute(self, statement):
                query = str(statement)
                if "current_database" in query:
                    return SimpleNamespace(scalar_one=lambda: "test_db")
                if "current_schema" in query:
                    return SimpleNamespace(scalar_one=lambda: "public")
                raise AssertionError("Unexpected SQL in mocked importer test.")

        class FakeBegin:
            def __init__(self):
                self.connection = FakeConnection()
                self.rolled_back = False
                self.committed = False

            def __enter__(self):
                return self.connection

            def __exit__(self, exc_type, exc, traceback):
                if exc_type is None:
                    self.committed = True
                else:
                    self.rolled_back = True
                return False

        fake_transaction = FakeBegin()
        validated_data = {
            "source_fingerprints": {"fixture.csv": "digest"},
        }
        env = {
            "BYTEBITE_TARGET_BRANCH": "synthetic-data-dev",
            "BYTEBITE_DEV_DB_HOST": "expected.test",
            "BYTEBITE_DEV_DB_NAME": "test_db",
            "BYTEBITE_STUDENT_ID_HMAC_KEY": "k" * 32,
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(importer, "check_target"),
            patch.object(importer, "validate_sources", return_value=validated_data),
            patch.object(importer, "verify_source_fingerprints"),
            patch.object(
                importer,
                "replacement_transaction",
                side_effect=importer.SQLAlchemyError("simulated database failure"),
            ),
            patch.object(importer.database.engine, "begin", return_value=fake_transaction),
            patch.object(
                sys,
                "argv",
                [
                    "import_synthetic_data.py",
                    "--replace-business-data",
                    "--confirm-target",
                    "synthetic-data-dev",
                ],
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = importer.main()

        self.assertEqual(result, 1)
        self.assertTrue(fake_transaction.rolled_back)
        self.assertFalse(fake_transaction.committed)

    def test_wrong_schema_rolls_back_before_replacement_starts(self):
        class FakeConnection:
            def execute(self, statement):
                query = str(statement)
                if "current_database" in query:
                    return SimpleNamespace(scalar_one=lambda: "test_db")
                if "current_schema" in query:
                    return SimpleNamespace(scalar_one=lambda: "not_public")
                raise AssertionError("Replacement must not execute for the wrong schema.")

        class FakeBegin:
            def __init__(self):
                self.rolled_back = False

            def __enter__(self):
                return FakeConnection()

            def __exit__(self, exc_type, exc, traceback):
                self.rolled_back = exc_type is not None
                return False

        fake_transaction = FakeBegin()
        env = {
            "BYTEBITE_TARGET_BRANCH": "synthetic-data-dev",
            "BYTEBITE_DEV_DB_HOST": "expected.test",
            "BYTEBITE_DEV_DB_NAME": "test_db",
            "BYTEBITE_STUDENT_ID_HMAC_KEY": "k" * 32,
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(importer, "check_target"),
            patch.object(importer, "validate_sources", return_value={
                "source_fingerprints": {"fixture.csv": "digest"},
            }),
            patch.object(importer.database.engine, "begin", return_value=fake_transaction),
            patch.object(importer, "replacement_transaction") as replacement_mock,
            patch.object(
                sys,
                "argv",
                [
                    "import_synthetic_data.py",
                    "--replace-business-data",
                    "--confirm-target",
                    "synthetic-data-dev",
                ],
            ),
            self.assertRaisesRegex(RuntimeError, "public schema"),
        ):
            importer.main()

        replacement_mock.assert_not_called()
        self.assertTrue(fake_transaction.rolled_back)

    def test_seed_admin_target_guard_rejects_missing_or_wrong_configuration(self):
        valid = {
            "BYTEBITE_TARGET_BRANCH": "synthetic-data-dev",
            "BYTEBITE_DEV_DB_NAME": "neondb",
            "BYTEBITE_DEV_DB_HOST": "expected.test",
        }
        invalid_environments = (
            {},
            {**valid, "BYTEBITE_TARGET_BRANCH": "wrong-branch"},
            {**valid, "BYTEBITE_DEV_DB_NAME": "wrong-db"},
            {key: value for key, value in valid.items() if key != "BYTEBITE_DEV_DB_HOST"},
        )
        for environment in invalid_environments:
            with self.subTest(environment_keys=sorted(environment)):
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaises(RuntimeError):
                        seed_admin.check_target()
        isolated_database.engine.connect.assert_not_called()

    def test_seed_admin_target_guard_rejects_mismatched_url_before_connecting(self):
        valid = {
            "BYTEBITE_TARGET_BRANCH": "synthetic-data-dev",
            "BYTEBITE_DEV_DB_NAME": "neondb",
            "BYTEBITE_DEV_DB_HOST": "expected.test",
        }
        with patch.dict(os.environ, valid, clear=True):
            with patch.object(isolated_database.engine.url, "host", "different.test"):
                with self.assertRaisesRegex(RuntimeError, "host"):
                    seed_admin.check_target()
            with patch.object(isolated_database.engine.url, "database", "other_db"):
                with self.assertRaisesRegex(RuntimeError, "database"):
                    seed_admin.check_target()
        isolated_database.engine.connect.assert_not_called()

    def test_seed_admin_target_guard_requires_live_neondb_public(self):
        valid = {
            "BYTEBITE_TARGET_BRANCH": "synthetic-data-dev",
            "BYTEBITE_DEV_DB_NAME": "neondb",
            "BYTEBITE_DEV_DB_HOST": "expected.test",
        }
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.__exit__.side_effect = lambda *_: connection.close()
        transaction = Mock()
        connection.begin.return_value = transaction
        identity_result = connection.execute.return_value.mappings.return_value
        identity_result.one.return_value = {
            "database_name": "neondb",
            "schema_name": "public",
        }
        isolated_database.engine.connect.side_effect = None
        isolated_database.engine.connect.return_value = connection

        with (
            patch.dict(os.environ, valid, clear=True),
            patch.object(isolated_database.engine.url, "database", "neondb"),
        ):
            seed_admin.check_target()

        connection.exec_driver_sql.assert_called_once_with("SET TRANSACTION READ ONLY")
        transaction.rollback.assert_called_once()
        connection.close.assert_called_once()

        identity_result.one.return_value = {
            "database_name": "wrong_db",
            "schema_name": "public",
        }
        isolated_database.engine.connect.reset_mock()
        with (
            patch.dict(os.environ, valid, clear=True),
            patch.object(isolated_database.engine.url, "database", "neondb"),
            self.assertRaisesRegex(RuntimeError, "live database target"),
        ):
            seed_admin.check_target()
        transaction.rollback.assert_called()

    def test_seed_admin_main_checks_target_before_password_or_account_session(self):
        with (
            patch.object(seed_admin, "check_target", side_effect=RuntimeError("unsafe target")),
            patch.object(seed_admin.getpass, "getpass") as password_prompt,
            patch.object(isolated_database, "get_db") as get_db,
            patch.object(
                sys,
                "argv",
                ["seed_admin.py", "--name", "Test", "--email", "test@example.test"],
            ),
            self.assertRaisesRegex(RuntimeError, "unsafe target"),
        ):
            seed_admin.main()
        password_prompt.assert_not_called()
        get_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
