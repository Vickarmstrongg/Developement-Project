"""Offline tests for migrate_lecturer_data.py. No database is used."""

import csv
import importlib.util
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

BACKEND = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "migrate_lecturer_data", BACKEND / "migrate_lecturer_data.py"
)
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)

T1 = "77fb2c0a-9f29-478f-bcd7-fb5e6967d9e8"
V1 = "b76dc24a-1ff3-4899-9138-2ab687901b70"
S1 = "70db8bbd-ea9b-4d60-92a8-72c949d7d44c"
TX1 = "e3157bac-cc77-45a6-99e7-4d9f08728088"
E1 = "30c10a5c-0969-4093-bde2-a0c0dee98e6b"


def write(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def build_dataset(directory: Path, tx_rows=None):
    H = migrate.HEADERS
    write(directory / "vendor_type.csv", H["vendor_type"], [[T1, "Restaurant"]])
    write(directory / "vendor.csv", H["vendor"],
          [[V1, "Place", "1 Street", "-33.9", "18.8", T1]])
    write(directory / "student.csv", H["student"], [[S1]])
    write(directory / "transaction.csv", H["transaction"],
          tx_rows if tx_rows is not None
          else [[TX1, S1, V1, "2023-01-01 18:53:00", "77.75", "0.05"]])
    write(directory / "calendar_event.csv", H["calendar_event"],
          [[E1, "welcoming", "Welcome", "2023-01-30", "2023-02-10", "university-wide", "false"]])


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.patch = patch.object(migrate, "EXPECTED_COUNTS", {
            "vendor_type": 1, "vendor": 1, "student": 1,
            "transaction": 1, "calendar_event": 1,
        })
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.food = patch.object(migrate, "FOOD_TYPES", {"Restaurant"})
        self.food.start()
        self.addCleanup(self.food.stop)

    def test_valid_dataset_passes_and_totals_are_exact(self):
        build_dataset(self.dir)
        summary = migrate.validate_sources(self.dir)
        self.assertTrue(summary["ok"], summary["issues"])
        self.assertEqual(summary["transactions"]["sum_value"], "77.75")
        self.assertEqual(summary["transactions"]["sum_discount"], "0.05")

    def test_missing_file_is_reported(self):
        build_dataset(self.dir)
        (self.dir / "student.csv").unlink()
        self.assertIn("missing_file", migrate.validate_sources(self.dir)["issues"])

    def test_student_file_with_personal_columns_is_rejected(self):
        build_dataset(self.dir)
        write(self.dir / "student.csv", ["id", "first_name"], [[S1, "X"]])
        self.assertIn("unexpected_columns", migrate.validate_sources(self.dir)["issues"])

    def test_unknown_student_and_duplicate_transaction_flagged(self):
        other = "11111111-1111-4111-8111-111111111111"
        build_dataset(self.dir, [
            [TX1, other, V1, "2023-01-01 18:53:00", "1.00", "0.05"],
            [TX1, S1, V1, "2023-01-01 18:53:00", "1.00", "0.05"],
        ])
        issues = migrate.validate_sources(self.dir)["issues"]
        self.assertIn("transaction_unknown_student", issues)
        self.assertIn("transaction_duplicate_id", issues)

    def test_bad_number_and_date_flagged(self):
        build_dataset(self.dir, [[TX1, S1, V1, "01/01/2023", "1e3", "x"]])
        issues = migrate.validate_sources(self.dir)["issues"]
        for name in ("transaction_bad_datetime", "transaction_bad_value",
                     "transaction_bad_discount"):
            self.assertIn(name, issues)


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "map.csv"

    def load(self, rows):
        write(self.path, ["user_id", "role", "vendor_source_uuid"], rows)
        return migrate.load_user_mapping(self.path, {V1})

    def test_valid_mapping(self):
        self.assertEqual(self.load([[5, "Staff", V1]])[5]["vendors"], [V1])

    def test_blank_vendor_rejected(self):
        with self.assertRaises(migrate.MigrationError):
            self.load([[5, "Staff", ""]])

    def test_unknown_vendor_rejected(self):
        with self.assertRaises(migrate.MigrationError):
            self.load([[5, "Manager", "22222222-2222-4222-8222-222222222222"]])

    def test_staff_with_two_vendors_rejected(self):
        with self.assertRaises(migrate.MigrationError):
            migrate.load_user_mapping(
                self._two(), {V1, "22222222-2222-4222-8222-222222222222"}
            )

    def _two(self):
        write(self.path, ["user_id", "role", "vendor_source_uuid"], [
            [5, "Staff", V1], [5, "Staff", "22222222-2222-4222-8222-222222222222"],
        ])
        return self.path

    def test_admin_rows_rejected(self):
        with self.assertRaises(migrate.MigrationError):
            self.load([[1, "Admin", V1]])


class TargetGuardTests(unittest.TestCase):
    def fake_database(self, host):
        module = ModuleType("database")
        module.engine = SimpleNamespace(url=SimpleNamespace(host=host))
        return module

    def run_guard(self, env, host="ep-test.example", confirm=migrate.TARGET_NAME):
        with patch.dict(os.environ, env, clear=True), \
                patch.dict(sys.modules, {"database": self.fake_database(host)}):
            return migrate.check_target(confirm)

    good = {
        "BYTEBITE_MIGRATION_TARGET": migrate.TARGET_NAME,
        "BYTEBITE_MIGRATION_DB_HOST": "ep-test.example",
        "BYTEBITE_MIGRATION_FORBIDDEN_DB_HOSTS": "ep-prod.example,ep-syn.example",
    }

    def test_passes_with_matching_settings(self):
        self.run_guard(self.good)

    def test_pooler_and_direct_hosts_are_the_same_endpoint(self):
        self.run_guard(self.good, host="ep-test-pooler.example")

    def test_deny_list_is_mandatory(self):
        env = {k: v for k, v in self.good.items() if "FORBIDDEN" not in k}
        with self.assertRaises(migrate.MigrationError):
            self.run_guard(env)

    def test_dev_host_variable_is_always_forbidden(self):
        env = {**self.good, "BYTEBITE_DEV_DB_HOST": "ep-test.example"}
        with self.assertRaises(migrate.MigrationError):
            self.run_guard(env)

    def test_stale_synthetic_target_branch_variable_refused(self):
        env = {**self.good, "BYTEBITE_TARGET_BRANCH": "synthetic-data-dev"}
        with self.assertRaises(migrate.MigrationError):
            self.run_guard(env)

    def test_wrong_confirm_flag(self):
        with self.assertRaises(migrate.MigrationError):
            self.run_guard(self.good, confirm="synthetic-data-dev")

    def test_missing_target_env(self):
        with self.assertRaises(migrate.MigrationError):
            self.run_guard({k: v for k, v in self.good.items() if k != "BYTEBITE_MIGRATION_TARGET"})

    def test_host_mismatch_refused(self):
        with self.assertRaises(migrate.MigrationError):
            self.run_guard(self.good, host="ep-other.example")

    def test_forbidden_host_refused(self):
        env = {**self.good, "BYTEBITE_MIGRATION_FORBIDDEN_DB_HOSTS": "ep-test.example"}
        with self.assertRaises(migrate.MigrationError):
            self.run_guard(env)

    def test_apply_requires_explicit_flags(self):
        args = migrate.build_parser().parse_args(["apply"])
        with self.assertRaises(migrate.MigrationError):
            migrate.cmd_apply(args)

    def test_confirmation_refused_without_terminal(self):
        with patch.object(sys, "stdin", SimpleNamespace(isatty=lambda: False)):
            with self.assertRaises(migrate.MigrationError):
                migrate.confirm_interactively("do it")

    def test_confirmation_needs_exact_text(self):
        with patch.object(sys, "stdin", SimpleNamespace(isatty=lambda: True)), \
                patch("builtins.input", return_value="yes"):
            with self.assertRaises(migrate.MigrationError):
                migrate.confirm_interactively("do it")


class MarkerTests(unittest.TestCase):
    class Result:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

        def scalar(self):
            return self.value[0] if self.value else None

    def connection(self, marker_host_hash, host="ep-test.example"):
        outer = self

        class Connection:
            engine = SimpleNamespace(url=SimpleNamespace(host=host))

            def execute(self, statement, params=None):
                sql = str(statement)
                if "to_regclass" in sql:
                    return outer.Result((True,))
                return outer.Result((marker_host_hash,) if marker_host_hash else None)

        return Connection()

    def test_marker_for_same_endpoint_accepted(self):
        migrate.require_marker(self.connection(migrate.host_fingerprint("ep-test-pooler.example")))

    def test_marker_for_other_endpoint_refused(self):
        with self.assertRaises(migrate.MigrationError):
            migrate.require_marker(self.connection(migrate.host_fingerprint("ep-prod.example")))

    def test_missing_marker_refused(self):
        with self.assertRaises(migrate.MigrationError):
            migrate.require_marker(self.connection(None))


class SchemaGuardTests(unittest.TestCase):
    def test_expected_foreign_keys_pass(self):
        rows = [("transactions", "students", "a"), ("transactions", "vendors", "a"),
                ("vendors", "vendor_types", "a"), ("users", "vendors", "a")]
        self.assertEqual(migrate.unexpected_foreign_keys(rows), [])

    def test_unknown_foreign_key_blocks(self):
        self.assertTrue(migrate.unexpected_foreign_keys([("reviews", "vendors", "a")]))

    def test_cascading_delete_blocks(self):
        self.assertTrue(migrate.unexpected_foreign_keys([("users", "vendors", "c")]))
        self.assertTrue(migrate.unexpected_foreign_keys([("users", "vendors", "n")]))


class SafetyInvariantTests(unittest.TestCase):
    """Pin properties that make the script safe, by inspecting its source."""

    source = (BACKEND / "migrate_lecturer_data.py").read_text(encoding="utf-8")

    def test_no_sequence_resets_or_destructive_ddl(self):
        code = self.source.split('"""', 2)[2]  # skip the module docstring
        for forbidden in ("TRUNCATE", "DROP TABLE", "DROP COLUMN", "DROP SCHEMA"):
            self.assertNotIn(forbidden, code)
        self.assertNotIn("SELECT setval", code)

    def test_legacy_context_events_never_referenced(self):
        self.assertNotRegex(self.source, r"public\.context_events")

    def test_deletes_only_in_clearing_and_load_phases(self):
        import inspect
        outside = self.source
        for function in (migrate.clear_synthetic_data, migrate.load_small_tables):
            outside = outside.replace(inspect.getsource(function), "")
        outside = outside.split('"""', 2)[2]
        self.assertNotIn("DELETE FROM", outside)

    def test_synthetic_transactions_only_deleted_where_not_lecturer(self):
        import inspect
        clearing = inspect.getsource(migrate.clear_synthetic_data)
        self.assertIn("source_uuid IS NULL", clearing)
        self.assertNotIn("LOCK TABLE", self.source.split('"""', 2)[2])

    def test_batch_data_and_progress_row_share_one_function(self):
        import inspect
        batch = inspect.getsource(migrate.load_batch)
        self.assertIn("INSERT INTO public.transactions", batch)
        self.assertIn("ON CONFLICT (source_uuid) DO NOTHING", batch)
        self.assertIn("{BATCH_TABLE}", batch)
        self.assertNotIn("engine.begin", batch)

    def test_apply_phase_order_and_direct_host(self):
        import inspect
        apply_source = (inspect.getsource(migrate.cmd_apply)
                        + inspect.getsource(migrate.apply_locked))
        order = ["require_direct=True", "MigrationSession", "snapshot_before_apply", "start_migration",
                 "clear_synthetic_data", "load_small_tables", "load_transactions", "finalize"]
        positions = [apply_source.index(name) for name in order]
        self.assertEqual(positions, sorted(positions))

    def test_complete_only_set_after_verify(self):
        import inspect
        finalize = inspect.getsource(migrate.finalize)
        self.assertLess(finalize.index("verify("), finalize.index("COMPLETE"))

    def test_gps_format_matches_rush_hour_parser(self):
        import re
        wkt = migrate.gps_wkt("-33.939553", "18.859011")
        match = re.match(r"POINT\(([-\d.]+)\s+([-\d.]+)\)", wkt)  # rush_hour.parse_gps
        self.assertEqual((float(match.group(2)), float(match.group(1))), (-33.939553, 18.859011))

    def test_mapping_and_snapshot_paths_are_git_ignored(self):
        ignore = (BACKEND.parent / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/migration/", ignore)
        self.assertIn("data/cleaned/", ignore)


def lost_error():
    return OperationalError("x", {}, Exception("the connection is lost"))


class FakePg:
    """One PostgreSQL server: a single advisory lock shared by many connections."""

    def __init__(self):
        self.holder = None

    def release_if_held(self, connection):
        if self.holder is connection:
            self.holder = None


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    def commit(self):
        self.connection.end("commit")

    def rollback(self):
        self.connection.end("rollback")


class FakeConn:
    def __init__(self, server, responder=None):
        self.server, self.responder = server, responder
        self.log, self.events = [], []   # (sql, params) / begin, commit, rollback
        self.in_tx = self.dead = self.closed = self.fail_commit = False

    def kill(self):
        """The server drops the session: its transaction vanishes and its lock is freed."""
        self.dead = True
        self.server.release_if_held(self)

    def in_transaction(self):
        return self.in_tx

    def begin(self):
        assert not self.in_tx, "nested transaction"
        self.in_tx = True
        self.events.append("begin")
        return FakeTransaction(self)

    def commit(self):
        self.end("commit")

    def rollback(self):
        self.end("rollback")

    def end(self, kind):
        if self.dead:
            raise lost_error()
        if kind == "commit" and self.fail_commit:
            self.kill()
            raise lost_error()
        self.in_tx = False
        self.events.append(kind)

    def close(self):
        self.closed = True
        self.server.release_if_held(self)

    def execute(self, statement, params=None):
        if self.dead:
            raise lost_error()
        sql = str(statement)
        self.in_tx = True
        self.log.append((sql, params))
        if "pg_try_advisory_lock" in sql:
            value = self.server.holder is None
            if value:
                self.server.holder = self
        elif "FROM pg_locks" in sql:
            value = 1 if self.server.holder is self else 0
        elif "pg_advisory_unlock" in sql:
            self.server.release_if_held(self)
            value = True
        else:
            value = self.responder(sql) if self.responder else 0
        return SimpleNamespace(scalar=lambda: value, first=lambda: None, all=lambda: [])

    def commits(self):
        return self.events.count("commit")


class FakeEngine:
    def __init__(self, server, responder=None):
        self.server, self.responder, self.created = server, responder, []

    def connect(self):
        connection = FakeConn(self.server, self.responder)
        self.created.append(connection)
        return connection


class BatchTests(unittest.TestCase):
    def test_batches_are_split_numbered_and_hashed(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [[f"id{i}", "s", "v", "2023-01-01 00:00:00", "1.00", "0.05"] for i in range(5)]
            build_dataset(Path(d), rows)
            batches = list(migrate.iter_batches(Path(d) / "transaction.csv", 2))
            again = list(migrate.iter_batches(Path(d) / "transaction.csv", 2))
        self.assertEqual([(n, len(r)) for n, r, _ in batches], [(0, 2), (1, 2), (2, 1)])
        self.assertEqual([h for *_, h in batches], [h for *_, h in again])
        self.assertEqual(len({h for *_, h in batches}), 3)

    def make_batches(self, count):
        with tempfile.TemporaryDirectory() as d:
            rows = [[f"id{i}", "s", "v", "2023-01-01 00:00:00", "1.00", "0.05"]
                    for i in range(count * 2)]
            build_dataset(Path(d), rows)
            return Path(d), list(migrate.iter_batches(Path(d) / "transaction.csv", 2))

    def run_load(self, done, max_batches, batch_size=2, total=3, rows=6):
        with tempfile.TemporaryDirectory() as d:
            data = [[f"id{i}", "s", "v", "2023-01-01 00:00:00", "1.00", "0.05"]
                    for i in range(rows)]
            build_dataset(Path(d), data)
            loaded = []
            state = {"batch_size": batch_size, "total_batches": total}
            with patch.object(migrate, "run_once",
                              side_effect=lambda e, w, **k: w("c")), \
                    patch.object(migrate, "committed_batches", return_value=done), \
                    patch.object(migrate, "load_batch",
                                 side_effect=lambda c, n, r, h, lock=None: loaded.append(n)):
                result = migrate.load_transactions(None, Path(d), state, max_batches)
        return result, loaded

    def test_resume_skips_committed_batches(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [[f"id{i}", "s", "v", "2023-01-01 00:00:00", "1.00", "0.05"] for i in range(6)]
            build_dataset(Path(d), rows)
            hashes = {n: h for n, _, h in migrate.iter_batches(Path(d) / "transaction.csv", 2)}
        done = {0: hashes[0], 1: hashes[1]}
        self.assertEqual(self.run_load(done, None), (True, [2]))

    def test_max_batches_stops_early_and_reports_incomplete(self):
        self.assertEqual(self.run_load({}, 1), (False, [0]))

    def test_changed_source_data_refuses_resume(self):
        with self.assertRaises(migrate.MigrationError):
            self.run_load({0: "different"}, None)

    def test_progress_beyond_file_refused(self):
        with self.assertRaises(migrate.MigrationError):
            self.run_load({7: "x"}, None)

    def test_pooler_host_refused_for_apply(self):
        module = ModuleType("database")
        module.engine = SimpleNamespace(url=SimpleNamespace(host="ep-test-pooler.example"))
        env = dict(TargetGuardTests.good)
        with patch.dict(os.environ, env, clear=True), \
                patch.dict(sys.modules, {"database": module}):
            with self.assertRaises(migrate.MigrationError):
                migrate.check_target(migrate.TARGET_NAME, require_direct=True)


class MigrationStatusTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "migration_status", BACKEND / "migration_status.py")
        self.status = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.status)

    def test_only_absent_or_complete_is_ready(self):
        self.assertTrue(self.status.is_ready("absent"))
        self.assertTrue(self.status.is_ready("complete"))
        for state in ("clearing", "loading", "validating", "unknown"):
            self.assertFalse(self.status.is_ready(state))


class LockTests(unittest.TestCase):
    def setup(self):
        server = FakePg()
        return server, FakeEngine(server)

    def test_acquire_then_release_on_exit(self):
        server, engine = self.setup()
        with migrate.MigrationSession(engine) as session:
            self.assertIs(server.holder, session.connection)
            session.check()
        connection = engine.created[0]
        self.assertIsNone(server.holder)
        self.assertTrue(connection.closed)
        self.assertTrue(any("pg_advisory_unlock" in q for q, _ in connection.log))

    def test_second_process_cannot_acquire_while_first_holds(self):
        server = FakePg()
        first_engine, second_engine = FakeEngine(server), FakeEngine(server)
        with migrate.MigrationSession(first_engine) as first:
            migrate.run_once(first, lambda c: c.execute(migrate.text("INSERT first")))
            with self.assertRaises(migrate.MigrationError) as raised:
                migrate.MigrationSession(second_engine).acquire()
            self.assertIn("Another migration process", str(raised.exception))
            refused = second_engine.created[0]
            self.assertTrue(refused.closed)
            logged = " ".join(q for q, _ in refused.log)
            for word in ("INSERT", "DELETE", "UPDATE", "CREATE", "ALTER"):
                self.assertNotIn(word, logged)
            self.assertIs(server.holder, first.connection)
        with migrate.MigrationSession(second_engine):  # free again after the first run ends
            pass

    def test_lock_released_when_the_work_fails(self):
        server, engine = self.setup()
        with self.assertRaises(RuntimeError):
            with migrate.MigrationSession(engine):
                raise RuntimeError("boom")
        self.assertIsNone(server.holder)
        self.assertTrue(engine.created[0].closed)

    def test_all_work_uses_the_one_lock_connection(self):
        server, engine = self.setup()
        seen = []
        with migrate.MigrationSession(engine) as session:
            holder = session.connection
            migrate.run_once(session, lambda c: seen.append(c))
            migrate.run_once(session, lambda c: seen.append(c))
            with session.connect() as connection:
                seen.append(connection)
            with session.begin() as connection:
                seen.append(connection)
        self.assertEqual(len(engine.created), 1)
        self.assertTrue(all(connection is holder for connection in seen))

    def test_connection_loss_aborts_and_never_switches_connection(self):
        server, engine = self.setup()
        with migrate.MigrationSession(engine) as session:
            connection = session.connection

            def work(c):
                c.execute(migrate.text("INSERT x"))
                connection.kill()
                raise lost_error()

            with self.assertRaises(migrate.MigrationError):
                migrate.run_once(session, work)
            self.assertTrue(session.lost)
            with self.assertRaises(migrate.MigrationError):
                migrate.run_once(session, lambda c: self.fail("must not run"))
            with self.assertRaises(migrate.MigrationError):
                session.check()
        self.assertEqual(len(engine.created), 1)
        self.assertEqual(connection.commits(), 1)  # only the lock acquisition itself

    def test_loss_immediately_before_commit_aborts(self):
        server, engine = self.setup()
        with migrate.MigrationSession(engine) as session:
            session.connection.fail_commit = True
            with self.assertRaises(migrate.MigrationError):
                migrate.run_once(session, lambda c: c.execute(migrate.text("INSERT x")))
            self.assertTrue(session.lost)
        self.assertEqual(engine.created[0].commits(), 1)
        self.assertEqual(len(engine.created), 1)

    def test_lock_gone_before_commit_prevents_the_commit(self):
        server, engine = self.setup()
        with migrate.MigrationSession(engine) as session:
            def work(c):
                c.execute(migrate.text("INSERT x"))
                server.holder = None

            with self.assertRaises(migrate.MigrationError):
                migrate.run_once(session, work)
            self.assertIn("rollback", session.connection.events)
        self.assertEqual(engine.created[0].commits(), 1)

    def test_a_dropped_process_cannot_commit_after_a_new_one_takes_over(self):
        server = FakePg()
        first_engine, second_engine = FakeEngine(server), FakeEngine(server)
        first = migrate.MigrationSession(first_engine)
        first.acquire()
        first.connection.kill()  # e.g. network drop: server frees the lock
        with migrate.MigrationSession(second_engine) as second:
            self.assertIs(server.holder, second.connection)
            with self.assertRaises(migrate.MigrationError):
                migrate.run_once(first, lambda c: c.execute(migrate.text("INSERT zombie")))
            self.assertEqual(first_engine.created[0].commits(), 1)
            self.assertIs(server.holder, second.connection)
        first.release()

    def test_apply_takes_lock_before_any_other_database_access(self):
        import inspect
        source = inspect.getsource(migrate.cmd_apply)
        self.assertLess(source.index("MigrationSession(engine)"), source.index("apply_locked("))
        self.assertNotIn("engine.connect", source)
        self.assertNotIn("run_once", source)

    def test_apply_path_never_opens_its_own_connection(self):
        import inspect
        for function in (migrate.cmd_apply, migrate.apply_locked, migrate.clear_synthetic_data,
                         migrate.load_transactions, migrate.finalize, migrate.start_migration,
                         migrate.load_small_tables, migrate.load_batch):
            source = inspect.getsource(function)
            for forbidden in ("engine.begin", "engine.connect", "create_engine", ".dispose("):
                self.assertNotIn(forbidden, source, function.__name__)
        self.assertNotIn("run_with_retry", self.source_text())
        self.assertNotIn("time_sleep", self.source_text())

    def source_text(self):
        return (BACKEND / "migrate_lecturer_data.py").read_text(encoding="utf-8")


class BatchAtomicityTests(unittest.TestCase):
    def run_batch(self, matched):
        server = FakePg()
        engine = FakeEngine(server, responder=lambda sql: matched if "lecturer_tx_stage s" in sql
                            and "count(*)" in sql else 0)
        rows = [["a"] * 6, ["b"] * 6]
        error = None
        with patch.object(migrate, "require_marker"), patch.object(migrate, "copy_text"):
            with migrate.MigrationSession(engine) as session:
                try:
                    migrate.run_once(session, lambda c: migrate.load_batch(c, 0, rows, "h", session))
                except migrate.MigrationError as raised:
                    error = str(raised)
        return error, engine.created[0]

    def ledger_written(self, connection):
        return any(f"INSERT INTO public.{migrate.BATCH_TABLE}" in q for q, _ in connection.log)

    def test_failed_batch_is_rolled_back_and_not_recorded(self):
        error, connection = self.run_batch(matched=1)
        self.assertIn("batch rolled back", error)
        self.assertFalse(self.ledger_written(connection))
        self.assertIn("rollback", connection.events)
        self.assertEqual(connection.commits(), 2)  # lock acquire + unlock; no batch commit

    def test_good_batch_commits_data_and_ledger_together(self):
        error, connection = self.run_batch(matched=2)
        self.assertIsNone(error)
        self.assertTrue(self.ledger_written(connection))
        self.assertEqual(connection.commits(), 3)  # acquire + the batch + unlock


class ResumeAndCompletionTests(unittest.TestCase):
    def test_new_process_resumes_from_committed_ledger_after_connection_loss(self):
        with tempfile.TemporaryDirectory() as d:
            build_dataset(Path(d), [[f"id{i}", "s", "v", "2023-01-01 00:00:00", "1.00", "0.05"]
                                    for i in range(6)])
            server, ledger, processed, crash = FakePg(), {}, [], {"on": 1}
            state = {"batch_size": 2, "total_batches": 3}
            holder = []

            def load(connection, number, rows, digest, lock=None):
                if number in ledger:
                    return
                if crash["on"] == number:
                    holder[0].connection.kill()
                    raise lost_error()
                ledger[number] = digest
                processed.append(number)

            with patch.object(migrate, "load_batch", side_effect=load), patch.object(
                    migrate, "committed_batches", side_effect=lambda c: dict(ledger)):
                with migrate.MigrationSession(FakeEngine(server)) as first:
                    holder.append(first)
                    with self.assertRaises(migrate.MigrationError):
                        migrate.load_transactions(first, Path(d), state, None, first)
                self.assertEqual(processed, [0])
                crash["on"] = None
                with migrate.MigrationSession(FakeEngine(server)) as second:
                    self.assertTrue(migrate.load_transactions(second, Path(d), state, None, second))
                self.assertEqual(processed, [0, 1, 2])

    def finalize_statuses(self, verify_effect):
        server = FakePg()
        engine = FakeEngine(server)
        with patch.object(migrate, "require_marker"), \
                patch.object(migrate, "_mapping_matches_users", return_value=[]), \
                patch.object(migrate, "verify", side_effect=verify_effect):
            with migrate.MigrationSession(engine) as session:
                try:
                    migrate.finalize(session, None, {}, {}, {}, {})
                except migrate.MigrationError:
                    pass
        return [p["s"] for q, p in engine.created[0].log if isinstance(p, dict) and "s" in p]

    def test_failed_validation_never_marks_complete(self):
        statuses = self.finalize_statuses(lambda *a: migrate.stop("mismatch"))
        self.assertIn("validating", statuses)
        self.assertNotIn("complete", statuses)

    def test_complete_is_set_only_after_validation_passes(self):
        statuses = self.finalize_statuses(lambda *a: None)
        self.assertEqual(statuses, ["validating", "complete"])

    def test_batch_size_change_blocks_resume(self):
        with self.assertRaises(migrate.MigrationError):
            migrate.check_resume_state({"dataset_fingerprint": "f", "batch_size": 1000}, "f", 5000)
        migrate.check_resume_state({"dataset_fingerprint": "f", "batch_size": 1000}, "f", 1000)


class FingerprintTests(unittest.TestCase):
    def fingerprint(self, d, mapping, **kw):
        args = dict(batch_size=100000, replace_events=True, purge=True)
        args.update(kw)
        return migrate.dataset_fingerprint(
            Path(d), args["batch_size"], args["replace_events"], args["purge"], mapping,
            **({"version": args["version"]} if "version" in args else {}))

    def test_mapping_file_version_and_settings_all_change_it(self):
        with tempfile.TemporaryDirectory() as d:
            build_dataset(Path(d))
            mapping = Path(d) / "mapping.csv"
            mapping.write_text("a\n", encoding="utf-8")
            base = self.fingerprint(d, mapping)
            self.assertEqual(base, self.fingerprint(d, mapping))
            self.assertNotEqual(base, self.fingerprint(d, mapping, version="other"))
            self.assertNotEqual(base, self.fingerprint(d, mapping, batch_size=5000))
            self.assertNotEqual(base, self.fingerprint(d, mapping, purge=False))
            self.assertNotEqual(base, self.fingerprint(d, mapping, replace_events=False))
            mapping.write_text("b\n", encoding="utf-8")
            self.assertNotEqual(base, self.fingerprint(d, mapping))

    def test_version_constant_is_in_the_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            build_dataset(Path(d))
            mapping = Path(d) / "m.csv"
            mapping.write_text("a\n", encoding="utf-8")
            with patch.object(migrate, "MIGRATION_VERSION", "different"):
                self.assertNotEqual(
                    migrate.dataset_fingerprint(Path(d), 5000, True, True, mapping),
                    self.fingerprint(d, mapping, batch_size=5000, version=migrate.MIGRATION_VERSION))


class ResumeAbortTests(unittest.TestCase):
    """cmd_apply on an existing run whose inputs changed must write nothing."""

    def run_resume(self, stored_fingerprint_for):
        with tempfile.TemporaryDirectory() as d:
            build_dataset(Path(d))
            mapping = Path(d) / "mapping.csv"
            mapping.write_text("user_id\n", encoding="utf-8")
            args = SimpleNamespace(
                replace_synthetic_data=True, user_vendor_map=str(mapping), batch_size=5000,
                max_batches=None, cleaned_dir=d, confirm_target=migrate.TARGET_NAME,
                replace_synthetic_events=True, purge_vendor_bound_records=True)
            stored = stored_fingerprint_for(Path(d), mapping)
            state = {"status": "loading", "dataset_fingerprint": stored, "batch_size": 5000}
            executed, writers = [], []

            class Conn:
                def execute(self, statement, params=None):
                    executed.append(str(statement))
                    return SimpleNamespace(scalar=lambda: 0)

            class FakeSession:
                def check(self):
                    pass

                @contextmanager
                def connect(self):
                    yield Conn()

            engine = object()
            fake_summary = {"ok": True, "_vendor_ids": set(), "transactions": {},
                            "files": {"transaction": 1}}
            names = ["start_migration", "clear_synthetic_data", "load_small_tables",
                     "load_transactions", "finalize", "run_once", "snapshot_before_apply"]
            patches = [patch.object(migrate, n, side_effect=lambda *a, n=n, **k: writers.append(n))
                       for n in names]
            with patch.object(migrate, "validate_sources", return_value=fake_summary), \
                    patch.object(migrate, "check_target", return_value=object()), \
                    patch.object(migrate, "migration_engine", return_value=engine), \
                    patch.object(migrate, "confirm_interactively"), \
                    patch.object(migrate, "MigrationSession") as lock_cls, \
                    patch.object(migrate, "require_marker"), \
                    patch.object(migrate, "table_exists", return_value=True), \
                    patch.object(migrate, "schema_problems", return_value=[]), \
                    patch.object(migrate, "_mapping_matches_users", return_value=[]), \
                    patch.object(migrate, "load_user_mapping", return_value={}), \
                    patch.object(migrate, "read_state", return_value=state):
                from contextlib import ExitStack
                with ExitStack() as stack:
                    for p in patches:
                        stack.enter_context(p)
                    class SessionCM:
                        def __enter__(self_inner): return FakeSession()
                        def __exit__(self_inner, *a): return False

                    lock_cls.return_value = SessionCM()
                    try:
                        migrate.cmd_apply(args)
                        error = None
                    except migrate.MigrationError as raised:
                        error = str(raised)
        return error, writers, executed

    def matching(self, d, mapping):
        return migrate.dataset_fingerprint(d, 5000, True, True, mapping)

    def test_unchanged_inputs_pass_the_guard(self):
        error, writers, _ = self.run_resume(self.matching)
        self.assertIsNone(error)
        self.assertIn("load_transactions", writers)
        self.assertNotIn("finalize", writers)  # a stopped/incomplete load never finalizes

    def test_changed_mapping_aborts_before_any_write(self):
        def stored(d, mapping):
            old = self.matching(d, mapping)
            mapping.write_text("user_id\nchanged\n", encoding="utf-8")  # edited after the run began
            return old
        error, writers, executed = self.run_resume(stored)
        self.assertIn("differ", error)
        self.assertEqual(writers, [])
        self.assertEqual([q for q in executed if "READ ONLY" not in q], [])

    def test_changed_version_aborts_before_any_write(self):
        def stored(d, mapping):
            return migrate.dataset_fingerprint(d, 5000, True, True, mapping, version="old-version")
        error, writers, executed = self.run_resume(stored)
        self.assertIn("differ", error)
        self.assertEqual(writers, [])
        self.assertEqual([q for q in executed if "READ ONLY" not in q], [])


class BatchLockTests(unittest.TestCase):
    class Conn:
        def __init__(self, rows):
            self.rows, self.sql = rows, []

        def execute(self, statement, params=None):
            sql = str(statement)
            self.sql.append(sql)
            count = self.rows
            return SimpleNamespace(first=lambda: None, scalar=lambda: count)

    def run_batch(self, lock):
        connection = self.Conn(2)
        rows = [["a"] * 6, ["b"] * 6]
        with patch.object(migrate, "require_marker"), patch.object(migrate, "copy_text"):
            try:
                migrate.load_batch(connection, 0, rows, "hash", lock)
                error = None
            except migrate.MigrationError as raised:
                error = str(raised)
        return error, connection.sql

    def test_lost_lock_prevents_the_batch_from_committing(self):
        def lost():
            migrate.stop("The migration lock was lost")

        error, sql = self.run_batch(SimpleNamespace(check=lost))
        self.assertIn("lock was lost", error)
        self.assertFalse(any(f"INSERT INTO public.{migrate.BATCH_TABLE}" in q for q in sql))

    def test_held_lock_lets_the_batch_record_its_ledger_row(self):
        error, sql = self.run_batch(SimpleNamespace(check=lambda: None))
        self.assertIsNone(error)
        self.assertTrue(any(f"INSERT INTO public.{migrate.BATCH_TABLE}" in q for q in sql))

    def test_transactions_pass_the_lock_into_every_batch(self):
        import inspect
        self.assertIn("load_batch(c, n, r, d, lock)", inspect.getsource(migrate.load_transactions))


class ResumeOrderTests(unittest.TestCase):
    def test_guard_precedes_snapshot_and_every_write_in_source(self):
        import inspect
        source = inspect.getsource(migrate.apply_locked)
        guard = source.index("check_resume_state(")
        for later in ("start_migration", "clear_synthetic_data",
                      "load_small_tables", "load_transactions", "finalize("):
            self.assertLess(guard, source.index(later), later)
        # snapshot and guard are in mutually exclusive branches: a resume never snapshots
        fresh = source.index("if state is None:")
        self.assertLess(fresh, source.index("snapshot_before_apply("))
        self.assertLess(source.index("snapshot_before_apply("), source.index("else:"))


if __name__ == "__main__":
    unittest.main()
