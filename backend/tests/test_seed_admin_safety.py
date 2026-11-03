#Safety tests for the Admin seeding script

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


BACKEND = Path(__file__).resolve().parents[1]


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
    security_stub = ModuleType("access.security")
    security_stub.hash_password = Mock(return_value="test-hash")
    global seed_admin, isolated_database
    isolated_database = database_stub
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
    sys.modules.pop("access.seed_admin", None)


class SeedAdminSafetyTests(unittest.TestCase):
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
