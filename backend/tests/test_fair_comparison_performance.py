from datetime import date, datetime
import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models
from fair_comparison import calculate_fair_comparison


class FairComparisonQueryTests(unittest.TestCase):
    def test_operational_tiers_use_one_grouped_transaction_query(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        models.Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        db = session_factory()

        db.add(models.VendorType(type_id=1, name="Cafe"))
        for vendor_id in (21, 22, 23):
            db.add(
                models.Vendor(
                    vendor_id=vendor_id,
                    name=f"Vendor {vendor_id}",
                    type_id=1,
                )
            )
        for vendor_id in (21, 22, 23):
            for student_number in (1, 2):
                db.add(
                    models.Transaction(
                        student_id=f"student-{vendor_id}-{student_number}",
                        vendor_id=vendor_id,
                        datetime=datetime(2026, 10, 28, 12, student_number),
                        value=10,
                    )
                )
        db.commit()

        query_count = 0

        def count_query(*_args):
            nonlocal query_count
            query_count += 1

        event.listen(engine, "before_cursor_execute", count_query)
        result = calculate_fair_comparison(db, 21, date(2026, 10, 28))
        event.remove(engine, "before_cursor_execute", count_query)

        self.assertEqual(query_count, 6)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["peer_group"]["participating_businesses"], 3)
        self.assertEqual(result["metrics"]["vendor_transactions"], 2)
        self.assertEqual(result["daily_trend"][0]["peer_average_transactions"], 2.0)

        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
