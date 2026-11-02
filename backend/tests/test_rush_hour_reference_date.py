from datetime import date, datetime
from types import SimpleNamespace
import unittest
from unittest import mock

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
import models
import reference_date
import rush_hour
from access.constants import Role
from access.deps import require_vendor_access, shape_for_role

# Sunday 1 Nov 2026 is "today"; the data runs on into December.
TODAY = date(2026, 11, 1)
# Wednesdays at or before TODAY: 14 Oct, 21 Oct, 28 Oct (and 7 Oct).
WEDNESDAYS = [date(2026, 10, 7), date(2026, 10, 14), date(2026, 10, 21), date(2026, 10, 28)]
FUTURE_WEDNESDAYS = [date(2026, 11, 4), date(2026, 11, 11), date(2026, 12, 2)]


def _fixed_today_reference(db):
    return reference_date.get_reference_date(db, today_provider=lambda: TODAY)


class RushHourReferenceDateBase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        for vendor_id in (1, 2, 3):
            self.db.add(models.Vendor(vendor_id=vendor_id, name=f"Vendor {vendor_id}", type_id=None))
        self.db.commit()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def add_day(self, vendor_id, day, students=6, per_student=1, hour=12):
        for index in range(students):
            for repeat in range(per_student):
                self.db.add(models.Transaction(
                    vendor_id=vendor_id,
                    student_id=f"v{vendor_id}-s{index}",
                    datetime=datetime(day.year, day.month, day.day, hour, repeat),
                    value=10,
                ))
        self.db.commit()


class ReferenceDateInRushHourTests(RushHourReferenceDateBase):
    def test_rush_hour_uses_the_shared_capped_helper(self):
        self.assertIs(rush_hour.get_reference_date, reference_date.get_reference_date)
        self.assertIs(main.get_reference_date, reference_date.get_reference_date)

    def test_future_rows_do_not_move_the_reference_date(self):
        self.add_day(1, date(2026, 10, 28))
        self.add_day(1, date(2026, 12, 30))
        self.assertEqual(_fixed_today_reference(self.db), TODAY)

    def test_baseline_weeks_end_on_the_capped_date(self):
        dates = rush_hour.get_last_n_occurrences(TODAY, 2, n=4)
        self.assertEqual(dates, WEDNESDAYS)
        self.assertTrue(all(d <= TODAY for d in dates))


class BulkStatusFutureDataTests(RushHourReferenceDateBase):
    def test_future_transactions_do_not_change_the_status(self):
        for day in WEDNESDAYS[:3]:
            self.add_day(1, day, students=6)
        self.add_day(1, WEDNESDAYS[3], students=6)
        before = rush_hour.get_bulk_vendor_status(
            self.db, [1], 2, 12, _fixed_today_reference(self.db)
        )
        for day in FUTURE_WEDNESDAYS:
            self.add_day(1, day, students=30, per_student=3)
        after = rush_hour.get_bulk_vendor_status(
            self.db, [1], 2, 12, _fixed_today_reference(self.db)
        )
        self.assertEqual(before, after)
        self.assertEqual(after[1]["status"], "ok")
        self.assertEqual(after[1]["level"], "normal")
        self.assertEqual(after[1]["student_count"], 6)

    def test_classifications_are_unchanged(self):
        for day in WEDNESDAYS[:3]:
            self.add_day(1, day, students=6)           # baseline 6
        self.add_day(1, WEDNESDAYS[3], students=6, per_student=2)   # 12 -> busy
        for day in WEDNESDAYS[:3]:
            self.add_day(2, day, students=6, per_student=2)         # baseline 12
        self.add_day(2, WEDNESDAYS[3], students=6)                   # 6 -> quiet
        result = rush_hour.get_bulk_vendor_status(self.db, [1, 2], 2, 12, TODAY)
        self.assertEqual(result[1]["level"], "busy")
        self.assertEqual(result[1]["recommendation"], "decrease")
        self.assertEqual(result[2]["level"], "quiet")
        self.assertEqual(result[2]["recommendation"], "increase")

    def test_privacy_suppression_is_unchanged(self):
        for day in WEDNESDAYS:
            self.add_day(1, day, students=4)
        result = rush_hour.get_bulk_vendor_status(self.db, [1], 2, 12, TODAY)
        self.assertEqual(result[1]["status"], "suppressed")
        self.assertIsNone(result[1]["level"])

    def test_future_students_cannot_lift_suppression(self):
        for day in WEDNESDAYS:
            self.add_day(1, day, students=2)
        for day in FUTURE_WEDNESDAYS:
            self.add_day(1, day, students=20)
        result = rush_hour.get_bulk_vendor_status(
            self.db, [1], 2, 12, _fixed_today_reference(self.db)
        )
        self.assertEqual(result[1]["status"], "suppressed")

    def test_future_only_vendor_has_no_usable_history(self):
        self.add_day(1, WEDNESDAYS[3])
        for day in FUTURE_WEDNESDAYS:
            self.add_day(2, day, students=20)
        result = rush_hour.get_bulk_vendor_status(
            self.db, [1, 2], 2, 12, _fixed_today_reference(self.db)
        )
        self.assertEqual(result[2]["status"], "suppressed")
        self.assertEqual(result[2]["student_count"], 0)

    def test_vendor_without_transactions_is_suppressed(self):
        self.add_day(1, WEDNESDAYS[3])
        result = rush_hour.get_bulk_vendor_status(self.db, [1, 3], 2, 12, TODAY)
        self.assertEqual(result[3]["status"], "suppressed")

    def test_no_reference_date_returns_safe_suppressed_results(self):
        self.assertIsNone(_fixed_today_reference(self.db))
        result = rush_hour.get_bulk_vendor_status(self.db, [1, 2], 2, 12, None)
        self.assertEqual(
            result,
            {v: {"status": "suppressed", "level": None, "student_count": 0} for v in (1, 2)},
        )


class WeeklyPatternFutureDataTests(RushHourReferenceDateBase):
    def test_future_transactions_do_not_change_the_pattern(self):
        for day in WEDNESDAYS:
            self.add_day(1, day, students=6)
        before = rush_hour.get_weekly_pattern(self.db, 1, _fixed_today_reference(self.db))
        for day in FUTURE_WEDNESDAYS:
            self.add_day(1, day, students=40, per_student=4)
        after = rush_hour.get_weekly_pattern(self.db, 1, _fixed_today_reference(self.db))
        self.assertEqual(before, after)
        self.assertEqual(len(after), 7 * 24)
        self.assertEqual(after["2-12"], "normal")
        self.assertEqual(after["2-3"], "suppressed")

    def test_future_only_vendor_is_fully_suppressed(self):
        self.add_day(1, WEDNESDAYS[3])
        for day in FUTURE_WEDNESDAYS:
            self.add_day(2, day, students=20)
        pattern = rush_hour.get_weekly_pattern(self.db, 2, _fixed_today_reference(self.db))
        self.assertEqual(set(pattern.values()), {"suppressed"})

    def test_empty_history_returns_a_complete_suppressed_grid(self):
        pattern = rush_hour.get_weekly_pattern(self.db, 1, None)
        self.assertEqual(len(pattern), 7 * 24)
        self.assertEqual(set(pattern.values()), {"suppressed"})


class EndpointTests(RushHourReferenceDateBase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(main, "get_reference_date", _fixed_today_reference)
        patch.start()
        self.addCleanup(patch.stop)

    def _user(self, role, all_vendors=False, vendor_ids=()):
        return SimpleNamespace(role=role, all_vendors=all_vendors, vendor_ids=list(vendor_ids))

    def test_radar_ignores_future_rows(self):
        for day in WEDNESDAYS:
            self.add_day(1, day, students=6)
        for day in FUTURE_WEDNESDAYS:
            self.add_day(1, day, students=30, per_student=3)
        admin = self._user(Role.ADMIN.value, all_vendors=True)
        result = main.rush_hour_radar(day=2, hour=12, db=self.db, user=admin)
        vendor = next(v for v in result["vendors"] if v["vendor_id"] == 1)
        self.assertEqual(vendor["level"], "normal")
        self.assertEqual(vendor["student_count"], 6)
        self.assertEqual(set(vendor), {
            "vendor_id", "name", "lat", "lon", "status", "level",
            "student_count", "recommendation", "mine",
        })
        self.assertTrue(vendor["mine"])

    def test_radar_on_empty_database_does_not_crash(self):
        admin = self._user(Role.ADMIN.value, all_vendors=True)
        result = main.rush_hour_radar(day=2, hour=12, db=self.db, user=admin)
        self.assertTrue(all(v["status"] == "suppressed" for v in result["vendors"]))

    def test_weekly_pattern_response_shape_and_future_exclusion(self):
        for day in WEDNESDAYS:
            self.add_day(1, day, students=6)
        for day in FUTURE_WEDNESDAYS:
            self.add_day(1, day, students=40, per_student=4)
        admin = self._user(Role.ADMIN.value, all_vendors=True)
        result = main.weekly_pattern(vendor_id=1, db=self.db, user=admin)
        self.assertEqual(set(result), {"vendor_id", "pattern"})
        self.assertEqual(result["pattern"]["2-12"], "normal")

    def test_vendor_access_rules_are_unchanged(self):
        admin = self._user(Role.ADMIN.value, all_vendors=True)
        manager = self._user(Role.MANAGER.value, vendor_ids=[1])
        staff = self._user(Role.STAFF.value, vendor_ids=[2])
        self.assertIs(require_vendor_access(3, admin), admin)
        self.assertIs(require_vendor_access(1, manager), manager)
        self.assertIs(require_vendor_access(2, staff), staff)
        for user, vendor_id in ((manager, 2), (staff, 1)):
            with self.assertRaises(HTTPException) as caught:
                require_vendor_access(vendor_id, user)
            self.assertEqual(caught.exception.status_code, 403)

    def test_staff_responses_still_have_no_revenue_fields(self):
        staff = self._user(Role.STAFF.value, vendor_ids=[1])
        shaped = shape_for_role(staff, {"vendor_id": 1, "pattern": {}, "revenue": 5})
        self.assertNotIn("revenue", shaped)


if __name__ == "__main__":
    unittest.main()
