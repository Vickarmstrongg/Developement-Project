from datetime import date, datetime
import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models
from rush_hour import get_bulk_vendor_status


class BulkVendorStatusAggregationTests(unittest.TestCase):
    def test_aggregates_counts_without_weakening_distinct_student_suppression(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        models.Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()

        vendor_ids = [21, 22, 23, 24]
        for vendor_id in vendor_ids:
            db.add(models.Vendor(vendor_id=vendor_id, name=f"Vendor {vendor_id}"))

        # Wednesday occurrences at or before 28 Oct 2026.
        dates = [date(2026, 10, 7), date(2026, 10, 14), date(2026, 10, 21)]

        # Vendor 21 has enough unique students across the sample window and
        # falls from a 10-transaction baseline to zero on the latest date.
        for occurrence_date in dates:
            for index in range(10):
                student_id = f"vendor-21-student-{index}"
                if db.get(models.Student, student_id) is None:
                    db.add(models.Student(id_number=student_id))
                db.add(
                    models.Transaction(
                        vendor_id=21,
                        student_id=student_id,
                        datetime=datetime.combine(
                            occurrence_date,
                            datetime.min.time(),
                        ).replace(hour=12),
                        value=10,
                    )
                )

        # Repeated students across days must count once for privacy.
        for occurrence_date in dates:
            for student_id in ("vendor-22-student-1", "vendor-22-student-2"):
                if db.get(models.Student, student_id) is None:
                    db.add(models.Student(id_number=student_id))
                db.add(
                    models.Transaction(
                        vendor_id=22,
                        student_id=student_id,
                        datetime=datetime.combine(
                            occurrence_date,
                            datetime.min.time(),
                        ).replace(hour=12),
                        value=10,
                    )
                )
            db.add(
                models.Transaction(
                    vendor_id=24,
                    student_id=None,
                    datetime=datetime.combine(
                        occurrence_date,
                        datetime.min.time(),
                    ).replace(hour=12),
                    value=10,
                )
            )
        db.commit()

        query_count = 0

        def count_query(*_args):
            nonlocal query_count
            query_count += 1

        event.listen(engine, "before_cursor_execute", count_query)
        statuses = get_bulk_vendor_status(
            db,
            vendor_ids,
            day_of_week=2,
            hour=12,
            reference_date=date(2026, 10, 28),
        )
        event.remove(engine, "before_cursor_execute", count_query)

        self.assertEqual(query_count, 1)
        self.assertEqual(statuses[21]["status"], "ok")
        self.assertEqual(statuses[21]["level"], "quiet")
        self.assertEqual(statuses[21]["student_count"], 10)
        self.assertEqual(statuses[22]["status"], "suppressed")
        self.assertEqual(statuses[22]["student_count"], 2)
        self.assertEqual(statuses[23]["status"], "suppressed")
        self.assertEqual(statuses[23]["student_count"], 0)
        self.assertEqual(statuses[24]["status"], "suppressed")
        self.assertEqual(statuses[24]["student_count"], 1)

        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
