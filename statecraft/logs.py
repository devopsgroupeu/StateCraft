#!/usr/bin/env python3
"""Structured JSON logging for StateCraft.

Emits one JSON object per log line on stdout, using a schema shared across the
OpenPrime services ({timestamp, level, service, message, requestId}) so Loki can
parse and correlate logs from every service the same way.
"""

import contextvars
import json
import logging
import re
import sys

SERVICE = "statecraft"

# Correlation id propagated from the caller via the X-Request-ID header (set by the
# API middleware). Included in every log line emitted while handling that request.
request_id_var = contextvars.ContextVar("request_id", default=None)

# Defence-in-depth: mask user:pass@ credentials in any logged string.
_URL_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


def _mask(text: str) -> str:
    return _URL_CREDENTIALS_RE.sub("://***:***@", text)


# Normalise Python level names to the backend's vocabulary (info/warn/error/debug).
_LEVEL_MAP = {"WARNING": "warn", "CRITICAL": "error"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": _LEVEL_MAP.get(record.levelname, record.levelname.lower()),
            "service": SERVICE,
            "message": _mask(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            entry["requestId"] = request_id
        if record.exc_info:
            entry["stack"] = self.formatException(record.exc_info)
        return json.dumps(entry)


# Configure the root logger with a single JSON handler on stdout (collected by Loki
# in Kubernetes). No file handler — matches the backend's console-only approach.
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
_root = logging.getLogger()
_root.handlers.clear()
_root.addHandler(_handler)
_root.setLevel(logging.INFO)

logger = logging.getLogger(SERVICE)
