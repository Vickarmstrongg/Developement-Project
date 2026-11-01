from datetime import date, datetime, timedelta
import unittest
from unittest import mock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models
import notifications
from notifications import check_transaction_change

TODAY = date(2026, 11, 1)  # a Sunday


def today():
    return TODAY


class NotificationReferenceDateTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(models.VendorType(type_id=1, name="Cafe"))
        for vendor_id in (1, 2):
            self.db.add(models.Vendor(vendor_id=vendor_id, name=f"V{vendor_id}", type_id=1))
        self.db.commit()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def add(self, vendor_id, day, count):
        self.db.bulk_insert_mappings(models.Transaction, [
            {
                "vendor_id": vendor_id,
                "student_id": f"s{i}",
                "datetime": datetime(day.year, day.month, day.day, 12, i % 60),
                "value": 10,
            }
            for i in range(count)
        ])
        self.db.commit()

    def add_weekly(self, vendor_id, target, baseline, actual):
        """Same-weekday history for the four weeks before target, then target."""
        for week in range(1, 5):
            self.add(vendor_id, target - timedelta(days=7 * week), baseline)
        self.add(vendor_id, target, actual)

    def check(self, vendor_id=1, user_id=1):
        check_transaction_change(self.db, vendor_id, user_id, today_provider=today)
        return self.db.query(models.Notification).all()

    def test_empty_history_creates_nothing(self):
        self.assertEqual(self.check(), [])

    def test_future_only_history_creates_nothing(self):
        self.add_weekly(1, date(2026, 12, 20), 10, 30)
        self.assertEqual(self.check(), [])

    def test_mixed_history_ignores_future_rows(self):
        # Complete day Saturday 31 Oct, with a spike versus its baseline
        self.add_weekly(1, date(2026, 10, 31), 10, 20)
        self.add(1, TODAY, 1)
        self.add_weekly(1, date(2026, 12, 26), 10, 1)
        found = self.check()
        self.assertEqual(len(found), 1)
        self.assertIn("[2026-10-31]", found[0].message)
        self.assertEqual(found[0].trigger_type, "transaction_increase")

    def test_message_date_never_after_today(self):
        self.add_weekly(1, date(2026, 10, 31), 10, 20)
        self.add_weekly(1, date(2026, 12, 26), 10, 1)
        for item in self.check():
            stamped = date.fromisoformat(item.message[1:11])
            self.assertLessEqual(stamped, TODAY)

    def test_today_is_skipped_as_incomplete(self):
        self.add_weekly(1, TODAY, 10, 25)
        self.assertEqual(self.check(), [])

    def test_latest_before_today_uses_latest_day(self):
        self.add_weekly(1, date(2026, 10, 24), 10, 20)
        found = self.check()
        self.assertEqual(len(found), 1)
        self.assertIn("[2026-10-24]", found[0].message)

    def test_decrease_and_boundaries(self):
        self.add_weekly(1, date(2026, 10, 24), 10, 7)  # -30%
        self.assertEqual(self.check()[0].trigger_type, "transaction_decrease")

    def test_inside_threshold_creates_nothing(self):
        self.add_weekly(1, date(2026, 10, 24), 10, 12)
        self.assertEqual(self.check(), [])

    def test_missing_baseline_week_creates_nothing(self):
        for week in (1, 2, 3):
            self.add(1, date(2026, 10, 24) - timedelta(days=7 * week), 10)
        self.add(1, date(2026, 10, 24), 30)
        self.assertEqual(self.check(), [])

    def test_duplicate_call_creates_one_notification(self):
        self.add_weekly(1, date(2026, 10, 24), 10, 20)
        self.check()
        self.assertEqual(len(self.check()), 1)

    def test_other_vendor_rows_are_ignored(self):
        self.add_weekly(2, date(2026, 10, 24), 10, 20)
        self.assertEqual(self.check(vendor_id=1), [])

    def test_notification_stored_for_calling_user_and_vendor(self):
        self.add_weekly(1, date(2026, 10, 24), 10, 20)
        item = self.check(vendor_id=1, user_id=7)[0]
        self.assertEqual((item.user_id, item.vendor_id), (7, 1))

    def test_reference_lookup_is_vendor_scoped(self):
        self.add_weekly(1, date(2026, 10, 24), 10, 20)
        self.add(2, date(2026, 10, 30), 5)
        with mock.patch.object(
            notifications, "get_reference_date", wraps=notifications.get_reference_date
        ) as spy:
            check_transaction_change(self.db, 1, 1, today_provider=today)
        self.assertIsNotNone(spy.call_args.kwargs["scope"])
        self.assertIn("[2026-10-24]", self.db.query(models.Notification).one().message)

    def test_query_count_is_two_for_no_notification(self):
        self.add_weekly(1, date(2026, 10, 24), 10, 10)
        statements = []
        listener = lambda conn, cur, stmt, *a: statements.append(stmt)
        event.listen(self.engine, "before_cursor_execute", listener)
        check_transaction_change(self.db, 1, 1, today_provider=today)
        event.remove(self.engine, "before_cursor_execute", listener)
        self.assertEqual(len(statements), 2)


if __name__ == "__main__":
    unittest.main()
