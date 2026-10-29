from datetime import datetime
import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models
from dashboard import _get_transaction_date_bounds


class DashboardDateBoundsTests(unittest.TestCase):
    def test_date_bounds_are_returned_by_one_scoped_query(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        models.Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()

        db.add_all(
            [
                models.Vendor(vendor_id=1, name="Vendor 1"),
                models.Vendor(vendor_id=2, name="Vendor 2"),
            ]
        )
        db.add_all(
            [
                models.Transaction(
                    vendor_id=1,
                    datetime=datetime(2026, 1, 5, 9),
                    value=10,
                ),
                models.Transaction(
                    vendor_id=1,
                    datetime=datetime(2026, 1, 8, 15),
                    value=10,
                ),
                models.Transaction(
                    vendor_id=2,
                    datetime=datetime(2025, 12, 1, 12),
                    value=10,
                ),
            ]
        )
        db.commit()

        query_count = 0

        def count_query(*_args):
            nonlocal query_count
            query_count += 1

        event.listen(engine, "before_cursor_execute", count_query)
        latest_date, earliest_date = _get_transaction_date_bounds(
            db.query(models.Transaction).filter(
                models.Transaction.vendor_id == 1
            )
        )
        event.remove(engine, "before_cursor_execute", count_query)

        self.assertEqual(query_count, 1)
        self.assertEqual(str(latest_date), "2026-01-08")
        self.assertEqual(str(earliest_date), "2026-01-05")

        db.close()
        engine.dispose()

    def test_empty_scope_returns_null_bounds(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        models.Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()

        self.assertEqual(
            _get_transaction_date_bounds(db.query(models.Transaction)),
            (None, None),
        )

        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
