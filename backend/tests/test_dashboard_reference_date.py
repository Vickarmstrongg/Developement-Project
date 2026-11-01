from datetime import date, datetime
from types import SimpleNamespace
import unittest
from unittest import mock

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import dashboard
import models
from access.constants import Role

TODAY = date(2026, 11, 1)
_REAL_BOUNDS = dashboard._get_transaction_date_bounds


def _real_date_bounds(scope):
    # SQLite returns date() as text; PostgreSQL returns real dates.
    latest, earliest = _REAL_BOUNDS(scope)
    if latest is None:
        return None, None
    return date.fromisoformat(latest), date.fromisoformat(earliest)


class ResolveDateWindowTests(unittest.TestCase):
    def test_default_window_ends_on_reference_and_spans_seven_days(self):
        start, end = dashboard._resolve_date_window(
            None, None, TODAY, date(2023, 1, 1)
        )
        self.assertEqual((start, end), (date(2026, 10, 26), TODAY))

    def test_short_history_starts_at_earliest_date(self):
        start, end = dashboard._resolve_date_window(
            None, None, TODAY, date(2026, 10, 30)
        )
        self.assertEqual((start, end), (date(2026, 10, 30), TODAY))

    def test_future_end_date_is_capped(self):
        _, end = dashboard._resolve_date_window(
            None, date(2026, 12, 31), TODAY, date(2023, 1, 1)
        )
        self.assertEqual(end, TODAY)

    def test_past_end_date_is_respected(self):
        start, end = dashboard._resolve_date_window(
            None, date(2025, 5, 10), TODAY, date(2023, 1, 1)
        )
        self.assertEqual((start, end), (date(2025, 5, 4), date(2025, 5, 10)))

    def test_explicit_historical_range_is_kept(self):
        start, end = dashboard._resolve_date_window(
            date(2024, 1, 1), date(2024, 1, 31), TODAY, date(2023, 1, 1)
        )
        self.assertEqual((start, end), (date(2024, 1, 1), date(2024, 1, 31)))


class DashboardOverviewReferenceDateTests(unittest.TestCase):
    def setUp(self):
        dashboard._overview_cache.clear()
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add_all([
            models.Vendor(vendor_id=1, name="Vendor 1"),
            models.Vendor(vendor_id=2, name="Vendor 2"),
        ])
        self.captured = {}
        patches = [
            mock.patch.object(dashboard, "today_in_app_timezone", return_value=TODAY),
            mock.patch.object(
                dashboard, "_get_transaction_date_bounds", _real_date_bounds
            ),
            mock.patch.object(dashboard, "_build_heatmap", self._fake_heatmap),
            mock.patch.object(dashboard, "get_bulk_vendor_status", self._fake_radar),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def _fake_heatmap(self, db, base_query):
        # PostgreSQL-only SQL is skipped; record exactly which rows would feed it.
        self.captured["heatmap_rows"] = [row.datetime for row in base_query.all()]
        return [
            {"day": day, "cells": [{"status": "no_data", "transactions": None}] * 6}
            for day in dashboard.DAY_NAMES
        ]

    def _fake_radar(self, db, vendor_ids, weekday, hour, reference_date):
        self.captured["radar_reference"] = reference_date
        return {}

    def _add(self, vendor_id, day, count=6, hour=9):
        for index in range(count):
            self.db.add(models.Transaction(
                vendor_id=vendor_id,
                student_id=f"{vendor_id}-{day.isoformat()}-{index}",
                datetime=datetime(day.year, day.month, day.day, hour),
                value=10,
            ))
        self.db.commit()

    def _user(self, role=Role.ADMIN.value, all_vendors=True, vendor_ids=None):
        return SimpleNamespace(
            role=role, all_vendors=all_vendors, vendor_ids=vendor_ids or []
        )

    def _overview(self, user=None, **params):
        args = {
            "start_date": None, "end_date": None, "vendor_id": None,
            "vendor_type": None,
        }
        args.update(params)
        return dashboard.get_dashboard_overview(
            db=self.db, current_user=user or self._user(), **args
        )

    def _seed_with_future(self):
        self._add(1, date(2026, 10, 28))
        self._add(1, date(2026, 11, 1))
        self._add(1, date(2026, 12, 25), count=9, hour=10)
        self._add(1, date(2026, 12, 31), count=9, hour=10)

    def test_default_range_ends_on_today_and_excludes_future(self):
        self._seed_with_future()
        result = self._overview()
        self.assertEqual(result["date_range"]["end"], "2026-11-01")
        self.assertEqual(result["date_range"]["start"], "2026-10-28")
        self.assertEqual(result["date_range"]["available_end"], "2026-11-01")
        self.assertEqual(result["date_range"]["available_start"], "2026-10-28")
        self.assertEqual(result["kpis"]["total_transactions"], 12)
        self.assertEqual(result["kpis"]["distinct_customers"], 12)
        self.assertEqual(result["kpis"]["revenue"], 120.0)
        self.assertEqual(result["kpis"]["vendors_covered"], 1)

    def test_trend_heatmap_and_radar_use_the_capped_range(self):
        self._seed_with_future()
        result = self._overview()
        self.assertEqual(
            [point["date"] for point in result["demand_trend"]],
            ["2026-10-28", "2026-11-01"],
        )
        self.assertTrue(self.captured["heatmap_rows"])
        self.assertTrue(
            all(moment.date() <= TODAY for moment in self.captured["heatmap_rows"])
        )

    def test_manual_future_end_date_is_capped(self):
        self._seed_with_future()
        result = self._overview(
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31)
        )
        self.assertEqual(result["date_range"]["end"], "2026-11-01")
        self.assertEqual(result["kpis"]["total_transactions"], 12)
        self.assertTrue(
            all(moment.date() <= TODAY for moment in self.captured["heatmap_rows"])
        )

    def test_future_only_start_date_is_rejected(self):
        self._seed_with_future()
        with self.assertRaises(HTTPException) as caught:
            self._overview(start_date=date(2026, 12, 25))
        self.assertEqual(caught.exception.status_code, 422)

    def test_historical_range_is_still_selectable(self):
        self._add(1, date(2025, 3, 3))
        self._seed_with_future()
        result = self._overview(
            start_date=date(2025, 3, 1), end_date=date(2025, 3, 31)
        )
        self.assertEqual(result["date_range"]["end"], "2025-03-31")
        self.assertEqual(result["kpis"]["total_transactions"], 6)

    def test_radar_reference_date_is_the_capped_date(self):
        self._seed_with_future()
        self._overview()
        self.assertEqual(self.captured["radar_reference"], TODAY)

    def test_empty_table_returns_no_data(self):
        result = self._overview()
        self.assertEqual(result["date_range"], {"start": None, "end": None})
        self.assertEqual(result["kpis"]["status"], "no_data")

    def test_only_future_transactions_returns_no_data(self):
        self._add(1, date(2026, 12, 25))
        result = self._overview()
        self.assertEqual(result["date_range"], {"start": None, "end": None})
        self.assertEqual(result["kpis"]["status"], "no_data")

    def test_sparse_history_starts_at_first_transaction(self):
        self._add(1, date(2026, 10, 31))
        self._add(1, date(2026, 12, 25))
        result = self._overview()
        self.assertEqual(result["date_range"]["start"], "2026-10-31")
        self.assertEqual(result["date_range"]["end"], "2026-11-01")
        self.assertEqual(result["kpis"]["total_transactions"], 6)

    def test_single_old_transaction_uses_its_own_date(self):
        self._add(1, date(2025, 6, 10))
        result = self._overview()
        self.assertEqual(result["date_range"]["end"], "2025-06-10")
        self.assertEqual(result["date_range"]["start"], "2025-06-10")

    def test_vendor_scope_is_used_for_the_reference_date(self):
        self._add(1, date(2026, 10, 20))
        self._add(2, date(2026, 10, 30))
        manager = self._user(
            role=Role.MANAGER.value, all_vendors=False, vendor_ids=[1]
        )
        result = self._overview(user=manager)
        self.assertEqual(result["date_range"]["end"], "2026-10-20")
        self.assertEqual(result["date_range"]["available_end"], "2026-10-20")
        self.assertEqual(result["kpis"]["total_transactions"], 6)
        self.assertEqual(result["kpis"]["vendors_covered"], 1)

    def test_scoped_user_cannot_see_other_vendors_future_or_past(self):
        self._add(1, date(2026, 10, 20))
        self._add(2, date(2026, 10, 30))
        self._add(2, date(2026, 12, 30))
        staff = self._user(
            role=Role.STAFF.value, all_vendors=False, vendor_ids=[2]
        )
        result = self._overview(user=staff)
        self.assertEqual(result["date_range"]["end"], "2026-11-01")
        self.assertEqual([p["date"] for p in result["demand_trend"]], ["2026-10-30"])
        self.assertEqual(result["kpis"]["total_transactions"], 6)
        self.assertNotIn("revenue", result["kpis"])

    def test_future_context_events_stay_available(self):
        self._seed_with_future()
        self.db.add_all([
            models.ContextualEvent(
                name="Upcoming exam week", event_type="assessment", scope="university-wide", source="test", updated_at=datetime(2026, 1, 1),
                start_date=date(2026, 11, 10), end_date=date(2026, 11, 20),
            ),
            models.ContextualEvent(
                name="Too far away", event_type="term", scope="university-wide", source="test", updated_at=datetime(2026, 1, 1),
                start_date=date(2027, 3, 1), end_date=date(2027, 3, 5),
            ),
        ])
        self.db.commit()
        result = self._overview()
        names = [event["name"] for event in result["upcoming_context_events"]]
        self.assertEqual(names, ["Upcoming exam week"])
        self.assertEqual(self.db.query(models.ContextualEvent).count(), 2)

    def test_cache_does_not_reuse_results_across_days(self):
        self._seed_with_future()
        first = self._overview()
        with mock.patch.object(
            dashboard, "today_in_app_timezone", return_value=date(2026, 12, 26)
        ):
            second = self._overview()
        self.assertEqual(first["date_range"]["end"], "2026-11-01")
        self.assertEqual(second["date_range"]["end"], "2026-12-26")

    def test_dashboard_never_modifies_transactions(self):
        self._seed_with_future()
        before = self.db.query(models.Transaction).count()
        self._overview()
        self.assertEqual(self.db.query(models.Transaction).count(), before)


if __name__ == "__main__":
    unittest.main()
