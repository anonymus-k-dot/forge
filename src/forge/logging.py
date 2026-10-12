"""Structured (JSON lines) logging and per-request correlation IDs.

Only the ``forge`` logger hierarchy is configured; Gunicorn's and other libraries' loggers
are left alone. Log records carry event names and metadata (categories, status codes,
durations) — not prompt text, model output, upstream error bodies, or credentials. The one
exception is ``enhance.internal_error``, which logs the traceback of an unexpected bug.
Structured fields are passed as ``extra={"forge": {...}}``.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import IO, Any

from flask import Flask, Response, g, has_request_context, request

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_HANDLER_MARKER = "_forge_handler"

logger = logging.getLogger("forge.http")


class RequestIdFilter(logging.Filter):
    """Attach the current request's ID (or ``None`` outside a request) to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = g.get("request_id") if has_request_context() else None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        fields = getattr(record, "forge", None)
        if isinstance(fields, dict):
            entry.update({k: v for k, v in fields.items() if k not in entry})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO", stream: IO[str] | None = None) -> logging.Logger:
    """Install the JSON handler on the ``forge`` logger. Safe to call repeatedly."""
    forge_logger = logging.getLogger("forge")
    forge_logger.setLevel(level.upper())
    forge_logger.propagate = False
    for handler in list(forge_logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            forge_logger.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stderr)
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    forge_logger.addHandler(handler)
    return forge_logger


def incoming_request_id(value: str | None) -> str:
    """Use a well-formed client-supplied ID, otherwise generate one.

    The pattern excludes whitespace and control characters, so IDs cannot inject log lines
    or headers.
    """
    if value and _VALID_REQUEST_ID.match(value):
        return value
    return uuid.uuid4().hex


def init_request_ids(app: Flask) -> None:
    """Assign every request an ID, echo it as ``X-Request-ID``, and log completion."""

    @app.before_request
    def _assign_request_id() -> None:
        g.request_id = incoming_request_id(request.headers.get(REQUEST_ID_HEADER))
        g.request_started = time.perf_counter()

    @app.after_request
    def _emit_request_id(response: Response) -> Response:
        request_id = g.get("request_id")
        if request_id is None:  # before_request did not run (e.g. failed earlier)
            request_id = g.request_id = incoming_request_id(None)
        response.headers[REQUEST_ID_HEADER] = request_id
        started = g.get("request_started")
        logger.info(
            "request.completed",
            extra={
                "forge": {
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "streamed": response.is_streamed,
                    # For streamed responses this is the time until headers, not the body.
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1)
                    if started is not None
                    else None,
                }
            },
        )
        return response
