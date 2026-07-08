"""Dependency-free structured (single-line JSON) logging for the worker.

CLAUDE.md requires single-line, grep-friendly log entries. The stdlib
``logging.basicConfig`` default formatter drops any ``extra={...}`` fields
attached to a record, so context such as ``address``/``namespace``/
``task_queue`` is silently lost. This module provides a ``logging.Formatter``
that emits one JSON object per record, including those extra fields.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging

# Attributes present on every stdlib LogRecord. Anything on a record that is
# NOT in this set was supplied by the caller via ``extra={...}`` and should be
# surfaced in the structured output. Kept in sync with CPython's LogRecord.
_STANDARD_LOGRECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Format each log record as a single-line JSON object.

    Always includes ``timestamp`` (UTC, ISO 8601), ``level``, ``logger`` and
    ``message``. Any non-standard attributes attached via ``extra={...}`` are
    merged in at the top level. Exception info, if present, is rendered into an
    ``exc_info`` string field.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": _dt.datetime.fromtimestamp(
                record.created, tz=_dt.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge any caller-supplied extras (record.__dict__ minus the standard
        # LogRecord attributes). Skip private keys and anything already set.
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOGRECORD_ATTRS or key.startswith("_"):
                continue
            if key in payload:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Install :class:`JsonFormatter` on the root logger's stream handler.

    Idempotent and dependency-free. Replaces any handlers previously installed
    by this function (or by ``basicConfig``) so log output stays single-line
    JSON.
    """
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    # Drop pre-existing handlers so we don't double-log or emit the default,
    # unstructured format alongside the JSON one.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
