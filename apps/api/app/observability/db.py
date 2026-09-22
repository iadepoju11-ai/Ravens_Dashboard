"""PostgreSQL instrumentation via SQLAlchemy engine events -- query
duration and error counts, without touching a single call site in
app/services/ or app/models/. Registered once per engine
(instrument_engine(db.engine), called from app/__init__.py after
db.init_app()).
"""

from __future__ import annotations

import time

from sqlalchemy import event

from app.observability.metrics import DB_ERRORS_TOTAL, DB_QUERY_DURATION_SECONDS

_START_TIME_KEY = "_observability_query_start"


def instrument_engine(engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        conn.info.setdefault(_START_TIME_KEY, []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        start_times = conn.info.get(_START_TIME_KEY)
        if start_times:
            DB_QUERY_DURATION_SECONDS.observe(time.perf_counter() - start_times.pop())

    @event.listens_for(engine, "handle_error")
    def _handle_error(exception_context):  # noqa: ANN001
        DB_ERRORS_TOTAL.inc()
        # Pop the matching start time too, if one was pushed -- a failed
        # statement never reaches after_cursor_execute, and leaving it
        # behind would attribute a later, unrelated query's duration to
        # this one on the next pop().
        start_times = exception_context.connection.info.get(_START_TIME_KEY) if exception_context.connection else None
        if start_times:
            start_times.pop()
