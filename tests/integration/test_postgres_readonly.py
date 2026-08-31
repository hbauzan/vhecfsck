"""Postgres read-only session tests (P7-04)."""

from __future__ import annotations

import pytest
from tests.integration.conftest import postgres_dsn
from vhecfsck.adapters.postgres_adapter import PostgresAdapter, parse_postgres_target
from vhecfsck.errors import UsageError

pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


def test_parse_strips_table_params_from_dsn() -> None:
    parsed = parse_postgres_target(
        "postgres://u:p@localhost:5432/db?table=t&column=v&connect_timeout=5"
    )
    assert "table=" not in parsed.dsn
    assert "column=" not in parsed.dsn
    assert "connect_timeout=5" in parsed.dsn


def test_missing_table_params_are_usage_errors() -> None:
    with pytest.raises(UsageError, match="table and column"):
        PostgresAdapter("postgres://u:p@localhost/db")


def test_write_on_audit_session_rejected_when_dsn_present() -> None:
    dsn = postgres_dsn()
    if dsn is None:
        pytest.skip("VHECFSCK_POSTGRES_DSN not set")
    psycopg = pytest.importorskip("psycopg")
    conn = psycopg.connect(
        dsn,
        autocommit=False,
        options="-c default_transaction_read_only=on",
    )
    try:
        conn.read_only = True
        with conn.cursor() as cur, pytest.raises(psycopg.Error):
            list(cur.stream("INSERT INTO _vhecfsck_no_table(x) VALUES (1)"))
    finally:
        conn.close()
