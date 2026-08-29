"""Postgres/pgvector adapter placeholder — class resolvable without the SDK."""

from __future__ import annotations

import importlib

from vhecfsck.errors import UsageError
from vhecfsck.logging import redact_secrets


class PostgresAdapter:
    """Structural stand-in until the postgres adapter ticket lands."""

    def __init__(self, target: str) -> None:
        """Open a pgvector table; requires the ``postgres`` optional extra."""
        try:
            importlib.import_module("psycopg")
        except ImportError as exc:
            safe = redact_secrets(target)
            raise UsageError(
                f"Postgres support is not installed (target={safe})",
                hint='pip install "vhecfsck[postgres]"',
            ) from exc
        safe = redact_secrets(target)
        raise UsageError(
            f"Postgres adapter is not implemented yet (target={safe})",
            hint="see roadmap phase P7 / postgres adapter tickets",
        )
