"""Unit tests for PostgresAdapter (P7-04) — no live server required."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scripts.check_readonly import check_file
from vhecfsck.adapters.postgres_adapter import (
    PostgresAdapter,
    dimension_from_format_type,
    index_kind_from_amname,
    metric_from_opclass,
    parse_postgres_target,
    parse_reloptions,
    plan_uses_index,
    quote_ident,
)
from vhecfsck.core.fragmentation import compute_dfi
from vhecfsck.errors import CapabilityError, UsageError
from vhecfsck.models import EvidenceStrength, IndexKind, MetricSpace

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_SRC = ROOT / "vhecfsck" / "adapters" / "postgres_adapter.py"


class _FakeCursor:
    def __init__(self, db: FakePostgres) -> None:
        self.db = db

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def stream(self, query: str, params: object = None) -> object:
        return iter(self.db.dispatch(query, params))


class FakePostgres:
    """In-memory catalog + table that speaks the adapter's SELECT dialect."""

    def __init__(
        self,
        *,
        dim: int = 4,
        n: int = 12,
        amname: str = "hnsw",
        opclass: str = "vector_l2_ops",
        dead: int = 3,
        superuser: bool = False,
        seq_scan: bool = False,
        iterative: str | None = "off",
        pgstattuple: tuple[int, int] | None = None,
        reloptions: str = "m=16,ef_construction=64",
    ) -> None:
        rng = np.random.default_rng(1)
        self.rows = [
            (i, rng.normal(size=dim).astype(np.float32).tolist()) for i in range(n)
        ]
        self.dim = dim
        self.amname = amname
        self.opclass = opclass
        self.dead = dead
        self.superuser = superuser
        self.seq_scan = seq_scan
        self.iterative = iterative
        self.pgstattuple_row = pgstattuple
        self.reloptions = reloptions
        self.read_only = False
        self.closed = False
        self._fetch_pending = False
        self._last_declare = ""
        self.info = type("Info", (), {"server_version": 160004})()
        self.writes: list[str] = []

    def cursor(self, _name: str | None = None) -> _FakeCursor:
        return _FakeCursor(self)

    def close(self) -> None:
        self.closed = True

    def dispatch(self, query: str, params: object) -> list[tuple[object, ...]]:
        q = " ".join(query.split())
        low = q.lower()
        if low.startswith("insert") or " insert " in f" {low} ":
            self.writes.append(q)
            msg = "cannot execute INSERT in a read-only transaction"
            raise RuntimeError(msg)
        if "current_setting('default_transaction_read_only')" in low:
            return [("on" if self.read_only else "off",)]
        if "current_setting('is_superuser')" in low:
            return [("on" if self.superuser else "off",)]
        if low.startswith("select version()"):
            return [("PostgreSQL 16.4",)]
        if "format_type" in low:
            return [(f"vector({self.dim})",)]
        if "pg_am" in low or "am.amname" in low:
            return [(self.amname, self.opclass, self.reloptions)]
        if "pg_stat_user_tables" in low:
            return [(len(self.rows), self.dead)]
        if "pgstattuple" in low:
            if self.pgstattuple_row is None:
                raise RuntimeError("extension not present")
            return [self.pgstattuple_row]
        if "pg_settings" in low:
            if self.iterative is None:
                return []
            return [("hnsw.iterative_scan", self.iterative)]
        if "set_config" in low:
            return [(str(params[1] if isinstance(params, tuple) else params),)]
        if low.startswith("explain"):
            node = "Seq Scan" if self.seq_scan else "Index Scan"
            plan = [{"Plan": {"Node Type": node}}]
            return [(plan,)]
        if low.startswith("declare"):
            self._fetch_pending = True
            self._last_declare = low
            return []
        if low.startswith("close"):
            self._fetch_pending = False
            return []
        if low.startswith("fetch"):
            if not self._fetch_pending:
                return []
            self._fetch_pending = False
            if "embedding" not in self._last_declare:
                return [(row[0],) for row in self.rows]
            return list(self.rows)
        if "order by" in low:
            return [(row[0],) for row in self.rows]
        if "= any" in low:
            wanted = set(params[0]) if isinstance(params, tuple) else set()
            return [row for row in self.rows if row[0] in wanted]
        return list(self.rows)


def _open(**kwargs: object) -> tuple[PostgresAdapter, FakePostgres]:
    db = FakePostgres(**kwargs)
    target = (
        "postgres://alice:s3cret@localhost:5432/vectors?table=items&column=embedding"
    )
    adapter = PostgresAdapter(target, connection=db)
    return adapter, db


def test_parse_and_quote_ident() -> None:
    parsed = parse_postgres_target(
        "postgres://alice:s3cret@db.example:5432/app?table=items&column=embedding"
        "&id_column=id&schema=public"
    )
    assert parsed.table == "items"
    assert parsed.column == "embedding"
    assert parsed.id_column == "id"
    assert "s3cret" in parsed.dsn
    assert "table=" not in parsed.dsn
    with pytest.raises(UsageError):
        parse_postgres_target("postgres://localhost/db")
    with pytest.raises(UsageError):
        quote_ident("items;drop")


def test_credentials_redacted_in_descriptor() -> None:
    adapter, _db = _open()
    try:
        assert "s3cret" not in adapter.descriptor.location
        # injected DSN has no password; location still redacts the raw target
        assert adapter.descriptor.engine == "pgvector"
        assert adapter.descriptor.index_kind is IndexKind.HNSW
        assert adapter.metric_space is MetricSpace.L2
    finally:
        adapter.close()


@pytest.mark.parametrize(
    ("opc", "expected"),
    [
        ("vector_l2_ops", MetricSpace.L2),
        ("vector_cosine_ops", MetricSpace.COSINE),
        ("vector_ip_ops", MetricSpace.DOT),
    ],
)
def test_metric_from_each_operator_class(opc: str, expected: MetricSpace) -> None:
    assert metric_from_opclass(opc) is expected


def test_index_kind_and_dimension_helpers() -> None:
    assert index_kind_from_amname("hnsw") is IndexKind.HNSW
    assert index_kind_from_amname("ivfflat") is IndexKind.IVF
    assert dimension_from_format_type("vector(1536)") == 1536
    with pytest.raises(UsageError):
        dimension_from_format_type("vector")
    assert parse_reloptions("m=16,ef_construction=64")["m"] == "16"


def test_plan_uses_index_detects_seq_scan() -> None:
    assert plan_uses_index([{"Plan": {"Node Type": "Index Scan"}}]) is True
    assert plan_uses_index([{"Plan": {"Node Type": "Seq Scan"}}]) is False


def test_session_is_marked_read_only() -> None:
    adapter, db = _open()
    try:
        assert db.read_only is True
    finally:
        adapter.close()


def test_superuser_warns_once() -> None:
    import vhecfsck.adapters.postgres_adapter as pa

    pa._SUPERUSER_WARNED = False
    with pytest.warns(UserWarning, match="superuser"):
        adapter, _db = _open(superuser=True)
        adapter.close()


def test_counts_are_proxy_not_exact() -> None:
    adapter, _db = _open(dead=5)
    try:
        caps = adapter.capabilities
        assert caps.report_deleted_counts is True
        assert caps.deleted_counts_exact is False
        counts = adapter.counts()
        assert counts.deleted == 5
        assert counts.exact is False
        result = compute_dfi(
            counts,
            report_deleted_counts=True,
            estimated=True,
            proxy=True,
        )
        assert result.detail["proxy"] is True
        assert result.detail["estimated"] is True
        assert result.evidence_strength is EvidenceStrength.MEDIUM
    finally:
        adapter.close()


def test_iter_fetch_search_echoes_params() -> None:
    adapter, _db = _open()
    try:
        seen = 0
        for batch in adapter.iter_live_vectors(batch_size=5):
            seen += int(batch.ids.shape[0])
        assert seen == 12
        sample = adapter.sample_ids(3, seed=2)
        fetched = adapter.fetch_vectors(sample)
        result = adapter.search(
            fetched.vectors, 4, params={"ef_search": 40, "nprobe": 2}
        )
        assert result.ids.shape == (3, 4)
        assert result.effective_params["ef_search"] == 40
        assert result.effective_params["index_used"] is True
        assert adapter.partitions() is None
    finally:
        adapter.close()


def test_seq_scan_is_capability_error_not_perfect_recall() -> None:
    adapter, _db = _open(seq_scan=True)
    try:
        queries = np.zeros((1, 4), dtype=np.float32)
        with pytest.raises(CapabilityError, match="index_not_used"):
            adapter.search(queries, 3, params={"ef_search": 8, "nprobe": 1})
    finally:
        adapter.close()


def test_close_blocks_use() -> None:
    adapter, db = _open()
    adapter.close()
    adapter.close()
    assert db.closed is True
    with pytest.raises(UsageError):
        adapter.counts()


def test_sql_literals_pass_readonly_guard() -> None:
    violations, exemptions = check_file(ADAPTER_SRC)
    assert violations == []
    assert exemptions == []


def test_explain_json_roundtrip_in_plan_helper() -> None:
    dumped = json.dumps([{"Plan": {"Node Type": "Bitmap Index Scan"}}])
    assert plan_uses_index(json.loads(dumped)) is True


def test_pgstattuple_overrides_pg_stat_when_present() -> None:
    adapter, _db = _open(pgstattuple=(9, 2), dead=99)
    try:
        counts = adapter.counts()
        assert counts.live == 9
        assert counts.deleted == 2
        assert counts.exact is False
    finally:
        adapter.close()


def test_ivfflat_echoes_lists_and_nprobe() -> None:
    adapter, _db = _open(
        amname="ivfflat",
        reloptions="lists=100",
        iterative=None,
    )
    try:
        assert adapter.descriptor.index_kind is IndexKind.IVF
        sample = adapter.sample_ids(2, seed=1)
        fetched = adapter.fetch_vectors(sample)
        result = adapter.search(
            fetched.vectors[:1], 3, params={"ef_search": 8, "nprobe": 5}
        )
        assert result.effective_params["nprobe"] == 5
        assert result.effective_params["lists"] == "100"
        assert "hnsw.iterative_scan" not in result.effective_params
        assert adapter.graph_stats() is None
    finally:
        adapter.close()


def test_empty_fetch_and_search_guards() -> None:
    adapter, _db = _open()
    try:
        empty = adapter.fetch_vectors(np.empty(0, dtype=np.int64))
        assert empty.ids.shape[0] == 0
        with pytest.raises(UsageError, match="batch_size"):
            next(adapter.iter_live_vectors(batch_size=0))
        with pytest.raises(UsageError, match="k must"):
            adapter.search(np.zeros((1, 4), dtype=np.float32), 0, params={})
        with pytest.raises(UsageError, match="unknown vector id"):
            adapter.fetch_vectors(np.array([999], dtype=np.int64))
    finally:
        adapter.close()
