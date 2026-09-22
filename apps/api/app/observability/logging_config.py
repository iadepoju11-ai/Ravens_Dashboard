"""Structured (JSON-lines) logging, replacing the default unstructured
text Flask/gunicorn log — every line is one JSON object, safe to ship to
any log aggregator without a custom parser, and carries the request_id/
tenant_id (app/observability/context.py) so a single request's log lines
can be correlated with each other and with the `request_id` returned in
every API response (see app/__init__.py's after_request hook).

Never a place to log secrets or raw request bodies (application
features/PII) — callers pass a message plus optional `extra={...}`
fields describing *what happened*, not raw payloads. This mirrors the
same discipline `ScoringRuntimeError` already applies to API responses,
just for a different audience (an operator reading logs, who is allowed
to see more than an API caller, but still never a credential or a raw
applicant feature vector).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

from app.observability.context import get_request_id, get_tenant_id

# Attributes every stdlib LogRecord already has -- anything else on the
# record came from a caller's `extra={...}` and should be included in the
# JSON output as its own field.
_STANDARD_LOG_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "tenant_id": get_tenant_id(),
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(app) -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # Flask's own app.logger otherwise adds a second, differently-formatted
    # handler of its own (Werkzeug's default) -- route everything through
    # the same JSON handler instead of having two log formats interleaved.
    app.logger.handlers = [handler]
    app.logger.setLevel(level)
    app.logger.propagate = False

    # gunicorn's own access/error loggers are separate logger instances
    # (`gunicorn.error`, `gunicorn.access`) that this call doesn't reach
    # when running under gunicorn (see apps/api/Dockerfile) -- acceptable
    # for this pass: application-level structured logs (this module) are
    # what request/scoring/DB/outbox/governance instrumentation writes to,
    # and gunicorn's own process-lifecycle lines staying in its default
    # format is a cosmetic gap, not a missing observability path.
