import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

import performance
from performance import PerformanceJSONResponse, PerformanceMiddleware


class PerformanceInstrumentationTests(unittest.TestCase):
    def test_request_log_contains_safe_timing_fields(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with patch.object(performance, "_enabled", True):
            performance.install_sqlalchemy_timing(engine)

        async def app(scope, receive, send):
            with engine.connect() as connection:
                connection.execute(text("SELECT 1")).all()
            response = PerformanceJSONResponse({"ok": True})
            await response(scope, receive, send)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def run_request():
            messages = []

            async def send(message):
                messages.append(message)

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/vendors/21/demand-forecast",
                "route": SimpleNamespace(path="/vendors/{vendor_id}/demand-forecast"),
            }
            await PerformanceMiddleware(app)(scope, receive, send)
            return messages

        with self.assertLogs("bytebite.performance", level="INFO") as logs:
            messages = asyncio.run(run_request())
        engine.dispose()

        payload = json.loads(logs.output[0].split("api_performance ", 1)[1])
        self.assertEqual(payload["endpoint"], "GET /vendors/{vendor_id}/demand-forecast")
        self.assertEqual(payload["status"], 200)
        self.assertIn("elapsed_ms", payload)
        self.assertEqual(payload["query_count"], 1)
        self.assertIn("db_execute_ms", payload)
        self.assertGreaterEqual(payload["db_execute_ms"], 0)
        self.assertIn("response_json_render", payload["stages"])
        self.assertEqual(messages[-1]["body"], b'{"ok":true}')
        self.assertNotIn("/vendors/21/", logs.output[0])


if __name__ == "__main__":
    unittest.main()
