from datetime import date, datetime, timezone
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
import reference_date
from reference_date import cap_reference_date, get_reference_date, today_in_app_timezone

TODAY = date(2026, 11, 1)


class CapReferenceDateTests(unittest.TestCase):
    def test_latest_before_today_is_used(self):
        self.assertEqual(cap_reference_date(date(2026, 10, 20), TODAY), date(2026, 10, 20))

    def test_latest_equal_to_today_is_used(self):
        self.assertEqual(cap_reference_date(TODAY, TODAY), TODAY)

    def test_future_latest_is_capped_to_today(self):
        self.assertEqual(cap_reference_date(date(2026, 12, 31), TODAY), TODAY)

    def test_datetime_is_reduced_to_a_date(self):
        self.assertEqual(
            cap_reference_date(datetime(2026, 12, 31, 21, 8), TODAY), TODAY)
        self.assertEqual(
            cap_reference_date(datetime(2026, 10, 31, 23, 59), TODAY), date(2026, 10, 31))

    def test_no_transactions_gives_none(self):
        self.assertIsNone(cap_reference_date(None, TODAY))


class GetReferenceDateTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        models.Transaction.__table__.create(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def add(self, vendor_id, when):
        self.db.add(models.Transaction(vendor_id=vendor_id, datetime=when, value=1))
        self.db.commit()

    def test_empty_table_returns_none(self):
        self.assertIsNone(get_reference_date(self.db, lambda: TODAY))

    def test_history_only_uses_latest_transaction(self):
        self.add(1, datetime(2026, 10, 20, 12))
        self.add(1, datetime(2026, 10, 25, 9))
        self.assertEqual(get_reference_date(self.db, lambda: TODAY), date(2026, 10, 25))

    def test_future_rows_do_not_move_the_date_past_today(self):
        self.add(1, datetime(2026, 10, 30, 12))
        self.add(1, datetime(2026, 12, 31, 21, 8))
        self.assertEqual(get_reference_date(self.db, lambda: TODAY), TODAY)

    def test_only_future_rows_still_gives_today(self):
        self.add(1, datetime(2027, 1, 5, 8))
        self.assertEqual(get_reference_date(self.db, lambda: TODAY), TODAY)

    def test_rows_are_never_changed(self):
        self.add(1, datetime(2026, 12, 31, 21, 8))
        get_reference_date(self.db, lambda: TODAY)
        self.assertEqual(self.db.query(models.Transaction).count(), 1)

    def test_scope_limits_which_transactions_count(self):
        self.add(1, datetime(2026, 10, 10, 12))
        self.add(2, datetime(2026, 10, 28, 12))
        scope = self.db.query(models.Transaction).filter(models.Transaction.vendor_id == 1)
        self.assertEqual(get_reference_date(self.db, lambda: TODAY, scope=scope),
                         date(2026, 10, 10))


class TodayTests(unittest.TestCase):
    def test_today_uses_johannesburg_not_utc(self):
        # 22:30 UTC on 31 Oct is already 1 Nov in South Africa (UTC+2).
        fixed = datetime(2026, 10, 31, 22, 30, tzinfo=timezone.utc)

        class FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed.astimezone(tz)

        with patch.object(reference_date, "datetime", FakeDatetime):
            self.assertEqual(today_in_app_timezone(), date(2026, 11, 1))

    def test_default_provider_returns_a_date(self):
        self.assertIsInstance(today_in_app_timezone(), date)
        self.assertNotIsInstance(today_in_app_timezone(), datetime)


if __name__ == "__main__":
    unittest.main()
