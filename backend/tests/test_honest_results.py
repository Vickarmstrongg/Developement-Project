import os
import unittest
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from honest_results import (
    _check_fair_comparison,
    _check_events,
    _forecast_backtest,
    _independent_forecast,
    _independent_radar_statuses,
    can_view_context_events,
    can_view_fair_comparison,
    can_view_revenue,
    compare_values,
    run_honest_results,
    validate_request_filters,
    validate_vendor_scope,
    CheckRequest,
)
from fastapi import HTTPException


class HonestResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        self.db = self.Session()
        self.db.query(models.Transaction).delete()
        self.db.query(models.ContextualEvent).delete()
        self.db.query(models.Student).delete()
        self.db.query(models.Vendor).delete()
        self.db.query(models.VendorType).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_matching_aggregate_passes_and_mismatch_fails(self):
        matching = compare_values(
            "transactions", "Transaction count", "2026-01-01 to 2026-01-07",
            12, 12, explanation="Independent count.",
        )
        mismatch = compare_values(
            "transactions", "Transaction count", "2026-01-01 to 2026-01-07",
            11, 12, explanation="Independent count.",
        )
        self.assertEqual(matching["status"], "PASS")
        self.assertEqual(mismatch["status"], "FAIL")
        self.assertEqual(mismatch["difference"], -1.0)

    def test_empty_data_is_not_marked_pass(self):
        result = compare_values(
            "revenue", "Revenue", "empty selection", None, None,
            no_data=True, explanation="No rows.",
        )
        self.assertEqual(result["status"], "NOT CHECKED")
        self.assertIn("no transaction data", result["reason"].lower())

    def test_forecast_has_seven_future_dates_and_leakage_free_backtest(self):
        first_day = date(2026, 1, 1)
        history = [
            {
                "date": first_day + timedelta(days=index),
                "orders": 10 + index,
                "revenue": float((10 + index) * 20),
                "customers": 8,
            }
            for index in range(60)
        ]
        points = _independent_forecast(history)
        backtest = _forecast_backtest(history)
        self.assertEqual(len(points), 7)
        self.assertEqual(points[0]["date"], (history[-1]["date"] + timedelta(days=1)).isoformat())
        self.assertEqual(backtest["holdout_days"], 28)
        self.assertTrue(backtest["training_uses_only_prior_dates"])

    def test_reversed_date_filter_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            validate_request_filters(CheckRequest(
                start_date=date(2026, 1, 2),
                end_date=date(2026, 1, 1),
            ))
        self.assertEqual(error.exception.status_code, 422)

    def test_invalid_event_type_filter_is_rejected(self):
        admin = SimpleNamespace(
            role="Admin", all_vendors=True, vendor_ids=[],
        )
        with self.assertRaises(HTTPException) as error:
            run_honest_results(
                CheckRequest(event_type="not-a-real-type"),
                self.db,
                admin,
            )
        self.assertEqual(error.exception.status_code, 422)

    def test_vendor_scope_rejects_unassigned_vendor(self):
        assigned = SimpleNamespace(all_vendors=False, vendor_ids=[4])
        validate_vendor_scope(4, assigned)
        with self.assertRaises(HTTPException) as error:
            validate_vendor_scope(5, assigned)
        self.assertEqual(error.exception.status_code, 403)

    def test_role_permissions_are_preserved(self):
        staff = SimpleNamespace(role="Staff", all_vendors=False, vendor_ids=[4])
        manager = SimpleNamespace(role="Manager", all_vendors=False, vendor_ids=[4])
        admin = SimpleNamespace(role="Admin", all_vendors=True, vendor_ids=[])
        self.assertFalse(can_view_revenue(staff))
        self.assertTrue(can_view_revenue(manager))
        self.assertFalse(can_view_fair_comparison(staff))
        self.assertTrue(can_view_fair_comparison(manager))
        self.assertFalse(can_view_context_events(manager))
        self.assertTrue(can_view_context_events(admin))
        fair_checks = _check_fair_comparison(None, staff, 4, None)
        self.assertEqual(fair_checks[0]["status"], "NOT CHECKED")
        self.assertIsNone(fair_checks[0]["application_result"])

    def test_staff_empty_report_does_not_include_revenue_values(self):
        staff = SimpleNamespace(role="Staff", all_vendors=False, vendor_ids=[])
        result = run_honest_results(CheckRequest(), self.db, staff)
        self.assertFalse(result["privacy_policy"]["revenue_available"])
        revenue_check = next(
            item for item in result["checks"]
            if item["id"] == "dashboard_revenue"
        )
        self.assertEqual(revenue_check["status"], "NOT CHECKED")
        self.assertIsNone(revenue_check["application_result"])
        self.assertNotIn("revenue", revenue_check)

    def test_context_event_filters_match_database_without_mutation(self):
        from datetime import timezone

        self.db.add_all([
            models.ContextualEvent(
                name="Academic dates",
                event_type="Academic Term",
                start_date=date(2026, 4, 1),
                end_date=date(2026, 4, 2),
                source="Test fixture",
                updated_at=datetime.now(timezone.utc),
            ),
            models.ContextualEvent(
                name="Campus event",
                event_type="Social Event",
                start_date=date(2025, 3, 1),
                end_date=date(2025, 3, 1),
                source="Test fixture",
                updated_at=datetime.now(timezone.utc),
            ),
        ])
        self.db.commit()
        count_before = self.db.query(func.count(models.ContextualEvent.event_id)).scalar()
        admin = SimpleNamespace(role="Admin")

        checks = _check_events(
            self.db,
            admin,
            CheckRequest(event_year=2026, event_type="Academic Term"),
        )

        count_after = self.db.query(func.count(models.ContextualEvent.event_id)).scalar()
        self.assertEqual(checks[0]["status"], "PASS")
        self.assertEqual(checks[0]["application_result"]["api_count"], 1)
        self.assertEqual(count_before, count_after)

    def test_radar_suppresses_fewer_than_five_distinct_students_read_only(self):
        self.db.add(models.VendorType(type_id=1, name="Cafe"))
        self.db.add(models.Vendor(vendor_id=1, name="Test Cafe", type_id=1))
        reference = date(2024, 2, 2)
        dates = [reference - timedelta(days=21), reference - timedelta(days=14),
                 reference - timedelta(days=7), reference]
        for student_number in range(4):
            student_id = f"test-student-{student_number}"
            self.db.add(models.Student(id_number=student_id))
            self.db.add(models.Transaction(
                student_id=student_id,
                vendor_id=1,
                datetime=datetime.combine(dates[student_number], time(12)),
                value=10,
                discount=0,
            ))
        self.db.commit()
        count_before = self.db.query(func.count(models.Transaction.transaction_id)).scalar()

        result = _independent_radar_statuses(
            self.db, [1], day_of_week=4, hour=12, reference_date=reference,
        )

        count_after = self.db.query(func.count(models.Transaction.transaction_id)).scalar()
        self.assertEqual(result[1], {"status": "suppressed", "level": None})
        self.assertEqual(count_before, count_after)
        self.assertNotIn("student_count", result[1])

    def test_empty_database_report_is_not_marked_fully_passed(self):
        admin = SimpleNamespace(role="Admin", all_vendors=True, vendor_ids=[])
        rows_before = self.db.query(func.count(models.Transaction.transaction_id)).scalar()

        result = run_honest_results(CheckRequest(), self.db, admin)

        rows_after = self.db.query(func.count(models.Transaction.transaction_id)).scalar()
        self.assertFalse(result["summary"]["fully_passed"])
        self.assertGreater(result["summary"]["not_checked"], 0)
        self.assertIn("REVIEW", result["summary"]["overall_status"])
        self.assertEqual(rows_before, rows_after)


if __name__ == "__main__":
    unittest.main()
