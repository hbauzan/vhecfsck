"""Structured logging with mandatory credential redaction.

Diagnostics go to stderr so stdout stays a clean machine-readable channel
for ``--format json`` report output (P3). There is no flag to disable
redaction — a hypothetical write path or leaked DSN is a security issue.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys

_REDACTED = "REDACTED"

# postgres://user:pass@host — password may contain URL-safe and regex-meta chars.
_POSTGRES = re.compile(r"(?i)\b(postgres(?:ql)?://[^:\s/]+:)([^@\s]+)(@)")
# Also catch generic user:pass@ in other DB URLs (mysql, etc.).
_GENERIC_DB = re.compile(r"(?i)\b((?:mysql|mongodb|redis)://[^:\s/]+:)([^@\s]+)(@)")
# ?api_key=... / &token=... query params
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:api[_-]?key|token|access[_-]?token|password|secret)=)([^&\s]+)"
)
# key=value forms for common secret names (not only query strings)
_ASSIGNED_SECRET = re.compile(
    r"(?i)\b((?:api[_-]?key|token|access[_-]?token|password|secret"
    r"|aws_secret_access_key)\s*[=:]\s*)(\S+)"
)
# Authorization: Bearer|Basic ...
_AUTH_HEADER = re.compile(r"(?i)\b(authorization:\s*(?:bearer|basic)\s+)(\S+)")
# Common opaque token shapes
_TOKEN_SHAPES = re.compile(r"(?i)\b((?:ghp_|sk-|AKIA)[A-Za-z0-9/+=_-]{8,})")
_ENV_SECRET_NAME = re.compile(r"(PASSWORD|SECRET|TOKEN|API_KEY)", re.IGNORECASE)

_LEVEL_BY_VERBOSITY: dict[int, int] = {
    -1: logging.ERROR,  # --quiet
    0: logging.WARNING,
    1: logging.INFO,  # -v
    2: logging.DEBUG,  # -vv
}


def redact_secrets(text: str) -> str:
    """Return ``text`` with credentials rewritten to ``REDACTED``.

    Safe for log records and for ``TargetDescriptor.location`` embedding in
    reports. Non-secret URLs such as ``file:///data/x.lance`` are unchanged.
    """
    if not text:
        return text
    out = text
    out = _POSTGRES.sub(rf"\1{_REDACTED}\3", out)
    out = _GENERIC_DB.sub(rf"\1{_REDACTED}\3", out)
    out = _QUERY_SECRET.sub(rf"\1{_REDACTED}", out)
    out = _ASSIGNED_SECRET.sub(rf"\1{_REDACTED}", out)
    out = _AUTH_HEADER.sub(rf"\1{_REDACTED}", out)
    out = _TOKEN_SHAPES.sub(_REDACTED, out)
    for name, value in os.environ.items():
        if not value or len(value) < 4 or not _ENV_SECRET_NAME.search(name):
            continue
        if value in out:
            out = out.replace(value, _REDACTED)
    return out


class RedactionFilter(logging.Filter):
    """Rewrite secret-bearing content on every log record.

    Applied by default to every handler. There is no disable switch.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Mutate ``record`` in place; always allow the record through."""
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: redact_secrets(val) if isinstance(val, str) else val
                    for key, val in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(*, verbosity: int = 0, log_format: str = "human") -> None:
    """Configure root ``vhecfsck`` logging to stderr with redaction.

    Args:
        verbosity: ``-1`` quiet, ``0`` default, ``1`` (``-v``), ``2`` (``-vv``).
        log_format: ``human`` (default) or ``json``.
    """
    if verbosity >= 2:
        level = logging.DEBUG
    else:
        level = _LEVEL_BY_VERBOSITY.get(verbosity, logging.WARNING)

    root = logging.getLogger("vhecfsck")
    root.handlers.clear()
    root.setLevel(level)
    root.propagate = False

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.addFilter(RedactionFilter())
    if log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
