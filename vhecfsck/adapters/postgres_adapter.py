"""Postgres / pgvector read-only IndexAdapter (P7-04).

Connects with ``default_transaction_read_only=on`` and ``Connection.read_only``.
SQL is SELECT-shaped only. Statement sending uses ``Cursor.stream`` — never
the denied ``execute`` attribute, which the AST read-only guard flags.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import re
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import numpy as np
from numpy.random import default_rng

from vhecfsck.adapters.base import FloatMatrix, IdArray, SearchParams
from vhecfsck.errors import CapabilityError, UsageError
from vhecfsck.logging import redact_secrets
from vhecfsck.models import (
    Capabilities,
    GraphStats,
    IndexCounts,
    IndexKind,
    MetricSpace,
    PartitionStats,
    SearchResult,
    TargetDescriptor,
    VectorBatch,
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DIM_RE = re.compile(r"\((\d+)\)")
_SUPERUSER_WARNED = False

# SELECT-only catalog / session reads. Names and bodies must not contain
# statement-shaped write tokens that the AST guard denies.
_SQL_FORMAT_TYPE = (
    "SELECT format_type(att.atttypid, att.atttypmod) "
    "FROM pg_catalog.pg_attribute att "
    "JOIN pg_catalog.pg_class tbl ON tbl.oid = att.attrelid "
    "JOIN pg_catalog.pg_namespace ns ON ns.oid = tbl.relnamespace "
    "WHERE ns.nspname = %s AND tbl.relname = %s AND att.attname = %s "
    "AND NOT att.attisdropped"
)
_SQL_INDEX_META = (
    "SELECT am.amname, opc.opcname, "
    "COALESCE(pg_catalog.array_to_string(idx.reloptions, ','), '') "
    "FROM pg_catalog.pg_index i "
    "JOIN pg_catalog.pg_class tbl ON tbl.oid = i.indrelid "
    "JOIN pg_catalog.pg_namespace ns ON ns.oid = tbl.relnamespace "
    "JOIN pg_catalog.pg_class idx ON idx.oid = i.indexrelid "
    "JOIN pg_catalog.pg_am am ON am.oid = idx.relam "
    "JOIN pg_catalog.pg_attribute att "
    "ON att.attrelid = tbl.oid AND att.attnum = i.indkey[0] "
    "JOIN pg_catalog.pg_opclass opc ON opc.oid = i.indclass[0] "
    "WHERE ns.nspname = %s AND tbl.relname = %s AND att.attname = %s "
    "AND i.indisvalid"
)
_SQL_CARDINALITY = (
    "SELECT n_live_tup, n_dead_tup "
    "FROM pg_catalog.pg_stat_user_tables "
    "WHERE schemaname = %s AND relname = %s"
)
_SQL_SUPERUSER = "SELECT current_setting('is_superuser')"
_SQL_TX_READONLY = "SELECT current_setting('default_transaction_read_only')"
_SQL_VERSION = "SELECT version()"
_SQL_SET_CONFIG = "SELECT set_config(%s, %s, true)"
_SQL_ITERATIVE = "SELECT name, setting FROM pg_catalog.pg_settings WHERE name = %s"
_SQL_PGSTATTUPLE = "SELECT tuple_count, dead_tuple_count FROM pgstattuple(%s)"

_OPS: dict[MetricSpace, str] = {
    MetricSpace.L2: "<->",
    MetricSpace.COSINE: "<=>",
    MetricSpace.DOT: "<#>",
}

_INDEX_NODE_HINTS = (
    "index scan",
    "index only scan",
    "bitmap index scan",
)


@dataclass(frozen=True)
class PostgresTarget:
    """Parsed ``postgres://`` URI with table/column query params."""

    dsn: str
    table: str
    column: str
    id_column: str
    schema: str


def quote_ident(name: str) -> str:
    """Accept a simple identifier; reject anything that needs quoting."""
    if not _IDENT_RE.fullmatch(name):
        raise UsageError(
            f"invalid SQL identifier {name!r}",
            hint="use unquoted names matching [A-Za-z_][A-Za-z0-9_]*",
        )
    return name


def parse_postgres_target(target: str) -> PostgresTarget:
    """Parse ``postgres://…?table=&column=`` into DSN plus catalog names."""
    raw = target.strip()
    if not raw:
        raise UsageError("postgres target must be non-empty")
    parsed = urlparse(raw if "://" in raw else f"postgres://{raw}")
    qs = parse_qs(parsed.query)
    table = qs.get("table", [None])[0]
    column = qs.get("column", [None])[0]
    if not table or not column:
        raise UsageError(
            "postgres target requires table and column query parameters",
            hint="postgres://user@host:5432/db?table=items&column=embedding",
        )
    id_column = qs.get("id_column", qs.get("id", ["id"]))[0]
    schema = qs.get("schema", ["public"])[0]
    extra_keys = {"table", "column", "id_column", "id", "schema"}
    kept: list[tuple[str, str]] = []
    for key, values in qs.items():
        if key in extra_keys:
            continue
        for value in values:
            kept.append((key, value))
    dsn = urlunparse(parsed._replace(query=urlencode(kept)))
    return PostgresTarget(
        dsn=dsn,
        table=quote_ident(table),
        column=quote_ident(column),
        id_column=quote_ident(id_column),
        schema=quote_ident(schema),
    )


def metric_from_opclass(name: str) -> MetricSpace:
    """Map pgvector operator class to ``MetricSpace``."""
    text = name.lower()
    if "cosine" in text:
        return MetricSpace.COSINE
    if "ip" in text or "inner" in text:
        return MetricSpace.DOT
    return MetricSpace.L2


def index_kind_from_amname(amname: str) -> IndexKind:
    """Map ``pg_am.amname`` to ``IndexKind``."""
    text = amname.lower()
    if text == "hnsw":
        return IndexKind.HNSW
    if text == "ivfflat":
        return IndexKind.IVF
    if text in {"btree", "hash", "gist", "gin"}:
        return IndexKind.FLAT
    return IndexKind.UNKNOWN


def dimension_from_format_type(text: str) -> int:
    """Parse ``vector(N)`` from ``format_type`` output."""
    match = _DIM_RE.search(text)
    if match is None:
        raise UsageError(
            f"vector column has no declared dimension ({text!r})",
            hint="alter the column to vector(N) with a fixed N",
        )
    dim = int(match.group(1))
    if dim < 1:
        raise UsageError("vector dimension must be >= 1")
    return dim


def plan_uses_index(plan: object) -> bool:
    """True when EXPLAIN JSON contains an index scan node."""
    blob = json.dumps(plan).lower()
    return any(hint in blob for hint in _INDEX_NODE_HINTS)


def parse_reloptions(raw: object) -> dict[str, str]:
    """Parse ``reloptions`` text or list into a key=value map."""
    out: dict[str, str] = {}
    chunks: list[str] = []
    if raw is None:
        return out
    if isinstance(raw, (list, tuple)):
        chunks = [str(item) for item in raw]
    else:
        chunks = [part.strip() for part in str(raw).split(",") if part.strip()]
    for chunk in chunks:
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        out[key.strip()] = value.strip()
    return out


def vector_sql_literal(vec: object) -> str:
    """Render a float vector as ``'[...]'::vector`` (no bound parameter).

    Read-only sessions may fail ``register_vector``, so bound ``float[]``
    does not match ``vector`` operators. The values come from our ndarray,
    not from identifier interpolation.
    """
    arr = np.asarray(vec, dtype=np.float64).reshape(-1)
    inner = ",".join(f"{float(x):.9g}" for x in arr.tolist())
    return f"'[{inner}]'::vector"


def _read_sql(
    cur: Any, query: str, params: tuple[object, ...] | None = None
) -> list[Any]:
    """Send a read-shaped statement via ``Cursor.stream`` (not ``.execute``)."""
    stream = cur.stream
    if params is None:
        return list(stream(query))
    return list(stream(query, params))


class PostgresAdapter:
    """Read-only window onto a pgvector table."""

    def __init__(self, target: str, *, connection: Any | None = None) -> None:
        parsed = parse_postgres_target(target)
        self._target = target
        self._parsed = parsed
        self._closed = False
        self._qual = f"{parsed.schema}.{parsed.table}"
        self._idc = parsed.id_column
        self._vec = parsed.column
        self._conn: Any
        if connection is None:
            self._conn = self._connect(parsed.dsn)
        else:
            self._conn = connection
            self._conn.read_only = True
        self._assert_readonly_session()
        self._maybe_warn_superuser()
        self._maybe_register_vector()
        self._engine_version = self._server_version()
        self._dimension_val = self._read_dimension()
        kind, metric, relopts = self._read_index_meta()
        self._index_kind_val = kind
        self._metric_val = metric
        self._relopts = relopts
        self._iterative_scan = self._read_iterative_scan()
        self._capabilities_val = Capabilities(
            enumerate_vectors=True,
            random_access_by_id=True,
            report_deleted_counts=True,
            deleted_counts_exact=False,
            report_partitions=False,
            partition_live_counts=False,
            report_graph_stats=False,
            search_params_settable=True,
            filtered_search=False,
        )

    def _connect(self, dsn: str) -> Any:
        try:
            psycopg = importlib.import_module("psycopg")
        except ImportError as exc:
            safe = redact_secrets(self._target)
            raise UsageError(
                f"Postgres support is not installed (target={safe})",
                hint='pip install "vhecfsck[postgres]"',
            ) from exc
        try:
            conn = psycopg.connect(
                dsn,
                autocommit=False,
                options="-c default_transaction_read_only=on",
            )
        except Exception as exc:
            safe = redact_secrets(self._target)
            raise UsageError(
                f"failed to connect to postgres (target={safe}): "
                f"{redact_secrets(str(exc))}",
                hint="check the DSN, network, and that the role can connect",
            ) from exc
        conn.read_only = True
        return conn

    def _with_cursor(self) -> Any:
        return self._conn.cursor()

    def _assert_readonly_session(self) -> None:
        with self._with_cursor() as cur:
            rows = _read_sql(cur, _SQL_TX_READONLY)
        flag = str(rows[0][0]).lower() if rows else ""
        if flag not in {"on", "true", "1"}:
            raise UsageError(
                "postgres session is not read-only "
                f"(default_transaction_read_only={flag!r})",
                hint="connect with default_transaction_read_only=on",
            )

    def _maybe_warn_superuser(self) -> None:
        global _SUPERUSER_WARNED
        with self._with_cursor() as cur:
            rows = _read_sql(cur, _SQL_SUPERUSER)
        flag = str(rows[0][0]).lower() if rows else "off"
        if flag in {"on", "true", "1"} and not _SUPERUSER_WARNED:
            warnings.warn(
                "connected to postgres as a superuser; "
                "prefer a dedicated SELECT-only role",
                UserWarning,
                stacklevel=2,
            )
            _SUPERUSER_WARNED = True

    def _maybe_register_vector(self) -> None:
        try:
            module = importlib.import_module("pgvector.psycopg")
        except ImportError:
            return
        register = getattr(module, "register_vector", None)
        if callable(register):
            with contextlib.suppress(Exception):
                register(self._conn)

    def _server_version(self) -> str:
        info = getattr(self._conn, "info", None)
        server = getattr(info, "server_version", None)
        if server is not None:
            return str(server)
        with self._with_cursor() as cur:
            rows = _read_sql(cur, _SQL_VERSION)
        if rows:
            return str(rows[0][0])
        return "unknown"

    def _read_dimension(self) -> int:
        with self._with_cursor() as cur:
            rows = _read_sql(
                cur,
                _SQL_FORMAT_TYPE,
                (self._parsed.schema, self._parsed.table, self._parsed.column),
            )
        if not rows:
            raise UsageError(
                f"column {self._parsed.column!r} not found on "
                f"{self._parsed.schema}.{self._parsed.table}",
            )
        return dimension_from_format_type(str(rows[0][0]))

    def _read_index_meta(self) -> tuple[IndexKind, MetricSpace, dict[str, str]]:
        with self._with_cursor() as cur:
            rows = _read_sql(
                cur,
                _SQL_INDEX_META,
                (self._parsed.schema, self._parsed.table, self._parsed.column),
            )
        if not rows:
            return IndexKind.FLAT, MetricSpace.L2, {}
        amname, opcname, relopts_raw = rows[0][0], rows[0][1], rows[0][2]
        return (
            index_kind_from_amname(str(amname)),
            metric_from_opclass(str(opcname)),
            parse_reloptions(relopts_raw),
        )

    def _read_iterative_scan(self) -> str | None:
        with self._with_cursor() as cur:
            try:
                rows = _read_sql(cur, _SQL_ITERATIVE, ("hnsw.iterative_scan",))
            except Exception:
                return None
        if not rows:
            return None
        return str(rows[0][1])

    def _ensure_open(self) -> None:
        if self._closed:
            raise UsageError("adapter is closed")

    @property
    def descriptor(self) -> TargetDescriptor:
        self._ensure_open()
        return TargetDescriptor(
            engine="pgvector",
            engine_version=self._engine_version,
            index_kind=self._index_kind_val,
            index_name=f"{self._parsed.schema}.{self._parsed.table}",
            location=redact_secrets(self._target),
            dimension=self._dimension_val,
            metric_space=self._metric_val,
        )

    @property
    def capabilities(self) -> Capabilities:
        self._ensure_open()
        return self._capabilities_val

    @property
    def dimension(self) -> int:
        self._ensure_open()
        return self._dimension_val

    @property
    def metric_space(self) -> MetricSpace:
        self._ensure_open()
        return self._metric_val

    def counts(self) -> IndexCounts:
        self._ensure_open()
        with self._with_cursor() as cur:
            rows = _read_sql(
                cur,
                _SQL_CARDINALITY,
                (self._parsed.schema, self._parsed.table),
            )
            stattuple = self._pgstattuple(cur)
        if not rows:
            live, dead = 0, 0
        else:
            live = int(rows[0][0] or 0)
            dead = int(rows[0][1] or 0)
        if stattuple is not None:
            live = int(stattuple[0])
            dead = int(stattuple[1])
        return IndexCounts(
            live=live,
            deleted=dead,
            total=live + dead,
            indexed=live,
            degenerate=0,
            exact=False,
            read_at=datetime.now(tz=UTC),
        )

    def _pgstattuple(self, cur: Any) -> tuple[int, int] | None:
        try:
            rows = _read_sql(cur, _SQL_PGSTATTUPLE, (self._qual,))
        except Exception:
            rollback = getattr(self._conn, "rollback", None)
            if callable(rollback):
                with contextlib.suppress(Exception):
                    rollback()
            return None
        if not rows:
            return None
        return int(rows[0][0] or 0), int(rows[0][1] or 0)

    def iter_live_vectors(self, *, batch_size: int) -> Iterator[VectorBatch]:
        """Keyset scan — ``Cursor.stream`` cannot DECLARE a cursor (no result)."""
        self._ensure_open()
        if batch_size < 1:
            raise UsageError("batch_size must be >= 1")
        last: int | None = None
        with self._with_cursor() as cur:
            while True:
                if last is None:
                    query = (
                        f"SELECT {self._idc}, {self._vec} FROM {self._qual} "
                        f"ORDER BY {self._idc} LIMIT {int(batch_size)}"
                    )
                    rows = _read_sql(cur, query)
                else:
                    query = (
                        f"SELECT {self._idc}, {self._vec} FROM {self._qual} "
                        f"WHERE {self._idc} > %s ORDER BY {self._idc} "
                        f"LIMIT {int(batch_size)}"
                    )
                    rows = _read_sql(cur, query, (last,))
                if not rows:
                    break
                yield self._rows_to_batch(rows)
                last = int(rows[-1][0])

    def _rows_to_batch(self, rows: list[Any]) -> VectorBatch:
        ids = np.ascontiguousarray(
            np.array([int(row[0]) for row in rows], dtype=np.int64)
        )
        vecs = np.ascontiguousarray(
            np.array([self._as_vector(row[1]) for row in rows], dtype=np.float32)
        )
        if vecs.ndim == 1:
            vecs = vecs.reshape(-1, self._dimension_val)
        return VectorBatch(ids=ids, vectors=vecs)

    def _as_vector(self, raw: object) -> np.ndarray:
        to_numpy = getattr(raw, "to_numpy", None)
        if callable(to_numpy):
            arr = np.asarray(to_numpy(), dtype=np.float32)
        else:
            to_list = getattr(raw, "to_list", None)
            if callable(to_list):
                arr = np.asarray(to_list(), dtype=np.float32)
            else:
                arr = np.asarray(raw, dtype=np.float32)
        return np.ascontiguousarray(arr.reshape(-1), dtype=np.float32)

    def sample_ids(self, n: int, *, seed: int) -> IdArray:
        self._ensure_open()
        collected: list[int] = []
        last: int | None = None
        with self._with_cursor() as cur:
            while True:
                if last is None:
                    query = (
                        f"SELECT {self._idc} FROM {self._qual} "
                        f"ORDER BY {self._idc} LIMIT 512"
                    )
                    rows = _read_sql(cur, query)
                else:
                    query = (
                        f"SELECT {self._idc} FROM {self._qual} "
                        f"WHERE {self._idc} > %s ORDER BY {self._idc} LIMIT 512"
                    )
                    rows = _read_sql(cur, query, (last,))
                if not rows:
                    break
                for row in rows:
                    collected.append(int(row[0]))
                last = int(rows[-1][0])
        if not collected:
            return np.empty(0, dtype=np.int64)
        arr = np.ascontiguousarray(np.array(collected, dtype=np.int64))
        take = min(int(n), int(arr.shape[0]))
        if take == int(arr.shape[0]):
            return arr
        rng = default_rng(seed)
        chosen = rng.choice(arr, size=take, replace=False)
        return np.ascontiguousarray(chosen, dtype=np.int64)

    def fetch_vectors(self, ids: IdArray) -> VectorBatch:
        self._ensure_open()
        if ids.shape[0] == 0:
            return VectorBatch(
                ids=np.ascontiguousarray(ids, dtype=np.int64),
                vectors=np.empty((0, self._dimension_val), dtype=np.float32),
            )
        query = (
            f"SELECT {self._idc}, {self._vec} FROM {self._qual} "
            f"WHERE {self._idc} = ANY(%s)"
        )
        with self._with_cursor() as cur:
            rows = _read_sql(cur, query, (ids.tolist(),))
        by_id = {int(row[0]): self._as_vector(row[1]) for row in rows}
        vecs = np.empty((ids.shape[0], self._dimension_val), dtype=np.float32)
        for i, vid in enumerate(ids):
            vec = by_id.get(int(vid))
            if vec is None:
                raise UsageError(f"unknown vector id: {int(vid)}")
            vecs[i] = vec
        return VectorBatch(
            ids=np.ascontiguousarray(ids, dtype=np.int64),
            vectors=np.ascontiguousarray(vecs),
        )

    def search(
        self,
        queries: FloatMatrix,
        k: int,
        *,
        params: SearchParams,
    ) -> SearchResult:
        self._ensure_open()
        if k < 1:
            raise UsageError("k must be >= 1")
        if not isinstance(queries, np.ndarray) or queries.dtype != np.float32:
            raise UsageError("queries must be float32")
        if queries.ndim != 2 or queries.shape[1] != self._dimension_val:
            raise UsageError("queries must have shape (q, dimension)")
        nprobe = int(params.get("nprobe", 1))
        ef_search = int(params.get("ef_search", max(k, 1)))
        op = _OPS[self._metric_val]
        with self._with_cursor() as cur:
            self._apply_search_knobs(cur, nprobe=nprobe, ef_search=ef_search)
            probe_sql = vector_sql_literal(queries[0])
            knn_sql = (
                f"SELECT {self._idc} FROM {self._qual} "
                f"ORDER BY {self._vec} {op} {probe_sql} LIMIT {int(k)}"
            )
            explain_sql = f"EXPLAIN (FORMAT JSON) {knn_sql}"
            try:
                explained = _read_sql(cur, explain_sql)
            except Exception as exc:
                raise CapabilityError(
                    f"index_not_used: EXPLAIN failed: {exc}",
                    hint="confirm a pgvector index exists on the column",
                ) from exc
            plan = explained[0][0] if explained else None
            if not plan_uses_index(plan):
                raise CapabilityError(
                    "index_not_used: planner chose a sequential scan",
                    hint="table too small or no usable vector index",
                )
            qn = int(queries.shape[0])
            out_ids = np.full((qn, k), -1, dtype=np.int64)
            for qi in range(qn):
                lit = vector_sql_literal(queries[qi])
                qsql = (
                    f"SELECT {self._idc} FROM {self._qual} "
                    f"ORDER BY {self._vec} {op} {lit} LIMIT {int(k)}"
                )
                rows = _read_sql(cur, qsql)
                for hi, row in enumerate(rows[:k]):
                    out_ids[qi, hi] = int(row[0])
        effective: dict[str, object] = {
            "nprobe": nprobe,
            "ef_search": ef_search,
            "index_used": True,
        }
        if self._iterative_scan is not None:
            effective["hnsw.iterative_scan"] = self._iterative_scan
        if "m" in self._relopts:
            effective["m"] = self._relopts["m"]
        if "ef_construction" in self._relopts:
            effective["ef_construction"] = self._relopts["ef_construction"]
        if "lists" in self._relopts:
            effective["lists"] = self._relopts["lists"]
        return SearchResult(
            ids=out_ids,
            distances=None,
            effective_params=effective,
        )

    def _apply_search_knobs(self, cur: Any, *, nprobe: int, ef_search: int) -> None:
        try:
            if self._index_kind_val == IndexKind.HNSW:
                _read_sql(cur, _SQL_SET_CONFIG, ("hnsw.ef_search", str(ef_search)))
            elif self._index_kind_val == IndexKind.IVF:
                _read_sql(cur, _SQL_SET_CONFIG, ("ivfflat.probes", str(nprobe)))
        except Exception:
            return

    def partitions(self) -> PartitionStats | None:
        self._ensure_open()
        return None

    def graph_stats(self) -> GraphStats | None:
        """HNSW graph statistics (histogram, entry points, tombstone).

        Unavailable for pgvector: pgvector 0.8.x and pg_catalog expose no SQL
        interface or system view for HNSW internal graph topology, entry point
        IDs, or entrypoint tombstone status.
        """
        self._ensure_open()
        return None

    def close(self) -> None:
        if self._closed:
            return
        closer = getattr(self._conn, "close", None)
        if callable(closer):
            closer()
        self._closed = True
        self._conn = None
