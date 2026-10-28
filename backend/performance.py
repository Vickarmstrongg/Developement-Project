"""Opt-in development performance instrumentation."""
from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
import json
import logging
import os
from time import perf_counter
from typing import Any, Callable, TypeVar

from fastapi.responses import JSONResponse
from sqlalchemy import event
from sqlalchemy.engine import Engine


_enabled = (
    os.getenv("APP_ENV", "").lower() in {"dev", "development", "local"}
    and os.getenv("BB_PERFORMANCE_LOGS", "").lower() in {"1", "true", "yes"}
)

_logger = logging.getLogger("bytebite.performance")
_T = TypeVar("_T")


class RequestMetrics:
    def __init__(self) -> None:
        self.started_at = perf_counter()
        self.query_count = 0
        self.db_execute_seconds = 0.0
        self.stages: dict[str, dict[str, float | int]] = {}


_request_metrics: ContextVar[RequestMetrics | None] = ContextVar(
    "bytebite_request_metrics",
    default=None,
)


def record_stage(name: str, duration_seconds: float) -> None:
    metrics = _request_metrics.get()
    if metrics is None:
        return

    stage = metrics.stages.setdefault(name, {"calls": 0, "duration_seconds": 0.0})
    stage["calls"] = int(stage["calls"]) + 1
    stage["duration_seconds"] = float(stage["duration_seconds"]) + duration_seconds


def timed_stage(name: str) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    def decorate(function: Callable[..., _T]) -> Callable[..., _T]:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> _T:
            started_at = perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                record_stage(name, perf_counter() - started_at)

        return wrapped

    return decorate


class PerformanceJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        started_at = perf_counter()
        try:
            return super().render(content)
        finally:
            record_stage("response_json_render", perf_counter() - started_at)


class PerformanceMiddleware:
    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        metrics = RequestMetrics()
        token = _request_metrics.set(metrics)
        status_code: int | None = None
        response_bytes = 0

        async def measured_send(message: dict[str, Any]) -> None:
            nonlocal status_code, response_bytes
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                response_bytes += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        except Exception:
            status_code = status_code or 500
            raise
        finally:
            route = scope.get("route")
            endpoint = getattr(route, "path", "<unmatched>")
            stages_ms = {
                name: {
                    "calls": values["calls"],
                    "duration_ms": round(float(values["duration_seconds"]) * 1000, 2),
                }
                for name, values in sorted(metrics.stages.items())
            }
            log_record = {
                "endpoint": f"{scope.get('method', 'UNKNOWN')} {endpoint}",
                "status": status_code,
                "elapsed_ms": round((perf_counter() - metrics.started_at) * 1000, 2),
                "query_count": metrics.query_count,
                "db_execute_ms": round(metrics.db_execute_seconds * 1000, 2),
                "response_bytes": response_bytes,
                "stages": stages_ms,
            }
            _logger.info("api_performance %s", json.dumps(log_record, sort_keys=True))
            _request_metrics.reset(token)


def install_sqlalchemy_timing(engine: Engine) -> None:
    if not _enabled or getattr(engine, "_bytebite_perf_timing", False):
        return

    setattr(engine, "_bytebite_perf_timing", True)

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        metrics = _request_metrics.get()
        if metrics is None:
            return
        metrics.query_count += 1
        connection.info.setdefault("_bytebite_perf_started_at", []).append(perf_counter())

    def finish_query(connection: Any) -> None:
        started_stack = connection.info.get("_bytebite_perf_started_at")
        if not started_stack:
            return
        elapsed = perf_counter() - started_stack.pop()
        if not started_stack:
            connection.info.pop("_bytebite_perf_started_at", None)
        metrics = _request_metrics.get()
        if metrics is not None:
            metrics.db_execute_seconds += elapsed

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        finish_query(connection)

    @event.listens_for(engine, "handle_error")
    def handle_error(exception_context: Any) -> None:
        if exception_context.connection is not None:
            finish_query(exception_context.connection)


def performance_logging_enabled() -> bool:
    return _enabled
