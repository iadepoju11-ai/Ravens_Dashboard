"""Request/correlation-id and tenant-id propagation, via `contextvars`
rather than Flask's `g` — `g` only exists inside an active application
context, which the logging formatter (module-level, used by every logger
in the process, including ones invoked from `flask <command>` CLI
commands with no request in flight) can't assume. A ContextVar reads
safely as `None` outside any context that set it.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def set_tenant_id(value: str | None) -> None:
    _tenant_id.set(value)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def reset_context() -> None:
    """Called at the start of each request (after any previous request's
    values on this worker) so a value never leaks from one request into
    the next — gunicorn's default sync worker reuses the same OS thread/
    process across requests, and ContextVars set with no explicit token
    reset otherwise persist for the life of that thread."""
    _request_id.set(None)
    _tenant_id.set(None)
