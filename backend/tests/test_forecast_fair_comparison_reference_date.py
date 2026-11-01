from datetime import date, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest import mock

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
import models
from access.constants import Role
from access.deps import require_vendor_access, shape_for_role
from demand_forecast import calculate_demand_forecast
from fair_comparison import calculate_fair_comparison

TODAY = date(2026, 11, 1)  # a Sunday
FAR_FUTURE = date(2030, 1, 1)


def today():
    return TODAY


class Base(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(models.VendorType(type_id=1, name="Cafe"))
        for vendor_id in (1, 2, 3, 4):
            self.db.add(models.Vendor(vendor_id=vendor_id, name=f"Vendor {vendor_id}", type_id=1))
        self.db.commit()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def add(self, vendor_id, day, count=1, value=10, hour=12):
        self.db.bulk_insert_mappings(models.Transaction, [
            {
                "vendor_id": vendor_id,
                "student_id": f"s{index}",
                "datetime": datetime(day.year, day.month, day.day, hour, index % 60),
                "value": value,
            }
            for index in range(count)
        ])
        self.db.commit()

    def add_history(self, vendor_id, start, end, count=1):
        day = start
        while day <= end:
            self.add(vendor_id, day, count)
            day += timedelta(days=1)


class DemandForecastReferenceDateTests(Base):
    def forecast(self, vendor_id=1, **kwargs):
        return calculate_demand_forecast(self.db, vendor_id, today_provider=today, **kwargs)

    def test_forecast_starts_after_today_not_after_future_data(self):
        self.add_history(1, date(2026, 10, 5), date(2026, 11, 1))
        self.add_history(1, date(2026, 12, 20), date(2026, 12, 31), count=9)
        result = self.forecast()
        self.assertEqual(result["history_to"], "2026-11-01")
        self.assertEqual(result["points"][0]["date"], "2026-11-02")
        self.assertEqual(result["points"][-1]["date"], "2026-11-08")
        self.assertEqual(result["horizon_days"], 7)

    def test_future_rows_do_not_change_any_figure(self):
        self.add_history(1, date(2026, 10, 5), date(2026, 11, 1))
        before = self.forecast()
        self.add_history(1, date(2026, 11, 2), date(2026, 12, 31), count=25)
        after = self.forecast()
        self.assertEqual(before, after)

    def test_comparison_weeks_ignore_future_days(self):
        self.add_history(1, date(2026, 10, 5), date(2026, 11, 1))
        self.add_history(1, date(2026, 11, 2), date(2026, 11, 8), count=30)
        result = self.forecast(selected_date="2026-11-02")
        week = result["historical_comparison"]
        self.assertEqual(week["selected_week_start"], "2026-11-02")
        self.assertTrue(all(day["this_week_orders"] is None for day in week["days"]))
        self.assertTrue(all(day["orders_change"] is None for day in week["days"]))

    def test_historical_only_data_is_unchanged_by_the_cap(self):
        self.add_history(1, date(2026, 9, 1), date(2026, 10, 25), count=2)
        capped = self.forecast()
        uncapped = calculate_demand_forecast(
            self.db, 1, today_provider=lambda: FAR_FUTURE
        )
        self.assertEqual(capped, uncapped)
        self.assertEqual(capped["history_to"], "2026-10-25")
        self.assertEqual(capped["points"][0]["date"], "2026-10-26")
        self.assertEqual(capped["points"][0]["expected_orders"], 2)
        self.assertEqual(capped["points"][0]["expected_revenue"], 20.0)

    def test_response_structure_is_unchanged(self):
        self.add_history(1, date(2026, 10, 5), date(2026, 11, 1))
        result = self.forecast()
        self.assertEqual(set(result), {
            "vendor_id", "vendor_name", "history_from", "history_to",
            "horizon_days", "points", "historical_comparison",
        })
        self.assertEqual(set(result["points"][0]), {
            "date", "day_of_week", "expected_orders", "expected_revenue",
            "expected_customers",
        })
        self.assertEqual(set(result["historical_comparison"]), {
            "selected_week_start", "selected_week_end", "previous_week_start",
            "previous_week_end", "days",
        })
        self.assertEqual(len(result["historical_comparison"]["days"]), 7)

    def test_future_only_vendor_has_no_history(self):
        self.add_history(2, date(2026, 10, 20), date(2026, 10, 25))
        self.add_history(1, date(2026, 12, 20), date(2026, 12, 25))
        self.assertEqual(
            self.forecast(1), {"error": "No transaction history for this vendor"}
        )

    def test_vendor_scope_sets_the_reference_date(self):
        self.add_history(1, date(2026, 10, 1), date(2026, 10, 10))
        self.add_history(2, date(2026, 10, 1), date(2026, 10, 25))
        self.assertEqual(self.forecast(1)["history_to"], "2026-10-10")
        self.assertEqual(self.forecast(2)["history_to"], "2026-10-25")

    def test_vendor_without_transactions_and_unknown_vendor(self):
        self.assertEqual(
            self.forecast(3), {"error": "No transaction history for this vendor"}
        )
        self.assertEqual(self.forecast(999), {"error": "Vendor not found"})

    def test_invalid_selected_date_is_still_rejected(self):
        self.add_history(1, date(2026, 10, 5), date(2026, 10, 25))
        self.assertEqual(
            self.forecast(selected_date="not-a-date"),
            {"error": "selected_date must use YYYY-MM-DD format"},
        )


class FairComparisonReferenceDateTests(Base):
    def compare(self, vendor_id=1, filter_date=None):
        return calculate_fair_comparison(
            self.db, vendor_id, filter_date, today_provider=today
        )

    def seed_peers(self):
        self.add_history(1, date(2026, 10, 26), date(2026, 11, 1), count=2)
        self.add_history(2, date(2026, 10, 26), date(2026, 11, 1))
        self.add_history(3, date(2026, 10, 26), date(2026, 11, 1))

    def test_default_window_ends_on_the_capped_date(self):
        self.seed_peers()
        self.add_history(1, date(2026, 12, 20), date(2026, 12, 31), count=40)
        result = self.compare()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["period"], {
            "start_date": "2026-10-26", "end_date": "2026-11-01",
        })
        self.assertEqual(result["metrics"]["vendor_transactions"], 14)
        self.assertEqual(result["metrics"]["peer_average_transactions"], 9.3)
        self.assertEqual(result["daily_trend"][-1]["date"], "2026-11-01")

    def test_future_rows_do_not_change_the_result(self):
        self.seed_peers()
        before = self.compare()
        for vendor_id in (1, 2, 3):
            self.add_history(vendor_id, date(2026, 11, 2), date(2026, 12, 31), count=20)
        self.assertEqual(self.compare(), before)

    def test_future_rows_do_not_change_the_size_tier(self):
        self.db.bulk_insert_mappings(models.Transaction, [
            {"vendor_id": 1, "student_id": "s", "datetime": datetime(2026, 10, 1, 9), "value": 1}
            for _ in range(1499)
        ])
        self.db.commit()
        self.add(1, date(2026, 12, 1), count=10)
        self.add(2, date(2026, 10, 1))
        self.add(3, date(2026, 10, 1))
        result = self.compare(filter_date=date(2026, 10, 1))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["peer_group"]["size_tier"], "small")

    def test_future_filter_date_is_not_served(self):
        self.seed_peers()
        for vendor_id in (1, 2, 3):
            self.add(vendor_id, date(2026, 12, 25), count=5)
        result = self.compare(filter_date=date(2026, 12, 25))
        self.assertEqual(result["status"], "suppressed")
        self.assertEqual(result["peer_group_size"], 0)

    def test_historical_filter_date_still_works(self):
        self.seed_peers()
        result = self.compare(filter_date=date(2026, 10, 28))
        self.assertEqual(result["period"], {
            "start_date": "2026-10-28", "end_date": "2026-10-28",
        })
        self.assertEqual(result["metrics"]["vendor_transactions"], 2)
        self.assertEqual(result["metrics"]["comparison_result"], "above_average")

    def test_historical_only_data_is_unchanged_by_the_cap(self):
        self.add_history(1, date(2026, 10, 1), date(2026, 10, 20), count=3)
        self.add_history(2, date(2026, 10, 1), date(2026, 10, 20))
        self.add_history(3, date(2026, 10, 1), date(2026, 10, 20))
        capped = self.compare()
        uncapped = calculate_fair_comparison(
            self.db, 1, None, today_provider=lambda: FAR_FUTURE
        )
        self.assertEqual(capped, uncapped)
        self.assertEqual(capped["period"]["end_date"], "2026-10-20")

    def test_response_structure_is_unchanged(self):
        self.seed_peers()
        result = self.compare()
        self.assertEqual(set(result), {
            "status", "vendor_id", "vendor_name", "period", "peer_group",
            "metrics", "daily_trend",
        })
        self.assertEqual(set(result["metrics"]), {
            "vendor_transactions", "peer_average_transactions", "vendor_revenue",
            "peer_average_revenue", "comparison_result",
        })
        self.assertEqual(len(result["daily_trend"]), 7)

    def test_future_only_history_is_suppressed_not_an_error(self):
        for vendor_id in (1, 2, 3):
            self.add_history(vendor_id, date(2026, 12, 20), date(2026, 12, 25))
        result = self.compare()
        self.assertEqual(result["status"], "suppressed")
        self.assertEqual(result["peer_group_size"], 0)

    def test_empty_database_returns_an_error(self):
        self.assertEqual(self.compare(), {"error": "No transaction data available"})

    def test_peer_minimum_is_unchanged(self):
        self.add_history(1, date(2026, 10, 26), date(2026, 11, 1))
        self.add_history(2, date(2026, 10, 26), date(2026, 11, 1))
        result = self.compare()
        self.assertEqual(result["status"], "suppressed")
        # Vendors 3 and 4 have no rows, but only 2 businesses had transactions.
        self.assertEqual(result["peer_group_size"], 2)

    def test_unknown_vendor(self):
        self.seed_peers()
        self.assertEqual(self.compare(999), {"error": "Vendor not found"})


class EndpointAndPermissionTests(Base):
    def _user(self, role, all_vendors=False, vendor_ids=()):
        return SimpleNamespace(
            role=role, all_vendors=all_vendors, vendor_ids=list(vendor_ids), user_id=1
        )

    def setUp(self):
        super().setUp()
        self.add_history(1, date(2026, 10, 5), date(2026, 11, 1))
        self.add_history(1, date(2026, 12, 20), date(2026, 12, 25), count=9)
        for name, target in (
            ("calculate_demand_forecast", main.calculate_demand_forecast),
            ("calculate_fair_comparison", main.calculate_fair_comparison),
        ):
            def wrapped(*args, _target=target, **kwargs):
                return _target(*args, today_provider=today, **kwargs)
            patch = mock.patch.object(main, name, wrapped)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(main.notifications, "check_transaction_change")
        patch.start()
        self.addCleanup(patch.stop)

    def test_admin_endpoint_uses_the_capped_date(self):
        admin = self._user(Role.ADMIN.value, all_vendors=True)
        result = main.get_demand_forecast(vendor_id=1, db=self.db, user=admin)
        self.assertEqual(result["history_to"], "2026-11-01")
        self.assertEqual(result["points"][0]["date"], "2026-11-02")

    def test_staff_forecast_still_has_no_revenue_fields(self):
        staff = self._user(Role.STAFF.value, vendor_ids=[1])
        result = main.get_demand_forecast(vendor_id=1, db=self.db, user=staff)
        self.assertEqual(result, shape_for_role(staff, result))
        self.assertNotIn("expected_revenue", result["points"][0])
        self.assertNotIn("this_week_revenue", result["historical_comparison"]["days"][0])

    def test_manager_forecast_keeps_revenue(self):
        manager = self._user(Role.MANAGER.value, vendor_ids=[1])
        result = main.get_demand_forecast(vendor_id=1, db=self.db, user=manager)
        self.assertIn("expected_revenue", result["points"][0])

    def test_fair_comparison_endpoint_returns_the_same_structure(self):
        result = main.get_fair_comparison(vendor_id=1, filter_date=None, db=self.db)
        self.assertIn(result["status"], {"ok", "suppressed"})

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

    def test_fair_comparison_route_still_requires_admin_or_manager(self):
        route = next(
            r for r in main.app.routes
            if getattr(r, "path", "") == "/vendors/{vendor_id}/fair-comparison"
        )
        names = [d.dependency.__name__ for d in route.dependencies]
        self.assertEqual(names[1:], ["checker", "require_vendor_access"])
        require_roles_dependency = route.dependencies[1].dependency
        staff = self._user(Role.STAFF.value, vendor_ids=[1])
        with self.assertRaises(HTTPException) as caught:
            require_roles_dependency(staff)
        self.assertEqual(caught.exception.status_code, 403)
        manager = self._user(Role.MANAGER.value, vendor_ids=[1])
        self.assertIs(require_roles_dependency(manager), manager)


if __name__ == "__main__":
    unittest.main()
