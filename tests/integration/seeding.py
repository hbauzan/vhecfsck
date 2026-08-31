# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""Deterministic corpus + index + churn seeding for Qdrant and pgvector.

Lives under ``tests/`` so write APIs never enter ``vhecfsck/`` (ADR-0001).
Both engines consume the same ``SeedPlan`` so later cross-engine tests share
one corpus, one index shape, and one churn pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from tests.integration.containers import (
    PostgresService,
    QdrantService,
    require_optional_import,
)
from vhecfsck.adapters.postgres_adapter import quote_ident
from vhecfsck.models import MetricSpace
from vhecfsck.synthetic.generator import GeneratedCorpus, generate_corpus

_QDRANT_DISTANCE = {
    MetricSpace.COSINE: "COSINE",
    MetricSpace.L2: "EUCLID",
    MetricSpace.DOT: "DOT",
}
_PG_OPCLASS = {
    MetricSpace.COSINE: "vector_cosine_ops",
    MetricSpace.L2: "vector_l2_ops",
    MetricSpace.DOT: "vector_ip_ops",
}
_PG_OPS = {
    MetricSpace.COSINE: "<=>",
    MetricSpace.L2: "<->",
    MetricSpace.DOT: "<#>",
}
_UPDATE_STREAM = 1_000_003


@dataclass(frozen=True)
class SeedSpec:
    """Corpus size, HNSW knobs, and churn counts for one seeded target."""

    n: int = 32
    dim: int = 8
    seed: int = 42
    metric_space: MetricSpace = MetricSpace.COSINE
    m: int = 8
    ef_construction: int = 32
    n_delete: int = 4
    n_update: int = 0
    n_clusters: int = 2
    name: str = "seeded"
    autovacuum: bool = True
    n_tenants: int = 0
    tenant_field: str = "tenant_id"
    payload_m: int | None = None
    indexing_threshold: int | None = None
    hnsw_full_scan_threshold: int | None = None


@dataclass(frozen=True)
class SeedPlan:
    """Arrays plus the spec that produced them — byte-identical at a fixed seed."""

    spec: SeedSpec
    corpus: GeneratedCorpus
    deleted_ids: tuple[int, ...]
    updated_ids: tuple[int, ...]
    update_vectors: NDArray[np.float32]
    tenant_of: tuple[str, ...]


def build_seed_plan(spec: SeedSpec | None = None) -> SeedPlan:
    """Build a deterministic corpus, deletion set, and optional update vectors."""
    spec = spec or SeedSpec()
    if spec.n < 1 or spec.dim < 1:
        raise ValueError("n and dim must be positive")
    if spec.n_clusters < 1 or spec.n_clusters > spec.n:
        raise ValueError("n_clusters must be in [1, n]")
    if spec.n_delete < 0 or spec.n_update < 0:
        raise ValueError("churn counts must be >= 0")
    if spec.n_delete + spec.n_update > spec.n:
        raise ValueError("n_delete + n_update must be <= n")
    if spec.n_tenants < 0:
        raise ValueError("n_tenants must be >= 0")
    if spec.payload_m is not None and spec.payload_m < 0:
        raise ValueError("payload_m must be >= 0")
    if spec.ef_construction < 1:
        raise ValueError("ef_construction must be >= 1")
    if spec.m == 0:
        if spec.payload_m is None or spec.payload_m < 2:
            raise ValueError("HNSW m=0 requires payload_m >= 2")
    elif spec.m < 2:
        raise ValueError("HNSW m must be >= 2 and ef_construction >= 1")

    corpus = generate_corpus(
        spec.n,
        spec.dim,
        n_clusters=spec.n_clusters,
        cluster_std=0.25,
        cluster_size_skew=0.0,
        seed=spec.seed,
        metric_space=spec.metric_space,
    )
    ids = [int(i) for i in corpus.ids.tolist()]
    deleted_ids = tuple(ids[-spec.n_delete :]) if spec.n_delete else ()
    live = ids[: spec.n - spec.n_delete]
    updated_ids = tuple(live[-spec.n_update :]) if spec.n_update else ()
    if spec.n_update:
        rng = np.random.default_rng(spec.seed + _UPDATE_STREAM)
        update_vectors = rng.standard_normal(
            (spec.n_update, spec.dim), dtype=np.float32
        )
    else:
        update_vectors = np.empty((0, spec.dim), dtype=np.float32)
    tenant_of: tuple[str, ...] = ()
    if spec.n_tenants > 0:
        tenant_of = tuple(
            f"t{int(vid) % spec.n_tenants}" for vid in corpus.ids.tolist()
        )
    return SeedPlan(
        spec=spec,
        corpus=corpus,
        deleted_ids=deleted_ids,
        updated_ids=updated_ids,
        update_vectors=update_vectors,
        tenant_of=tenant_of,
    )


def apply_qdrant(service: QdrantService, plan: SeedPlan) -> None:
    """Create a collection, upsert the corpus, then apply delete/update churn."""
    require_optional_import("qdrant_client", extra="qdrant")
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    name = plan.spec.name
    distance = getattr(models.Distance, _QDRANT_DISTANCE[plan.spec.metric_space])
    client = QdrantClient(host=service.host, port=service.http_port, prefer_grpc=False)
    try:
        hnsw_kwargs: dict[str, int] = {
            "m": plan.spec.m,
            "ef_construct": plan.spec.ef_construction,
        }
        if plan.spec.payload_m is not None:
            hnsw_kwargs["payload_m"] = int(plan.spec.payload_m)
        if plan.spec.hnsw_full_scan_threshold is not None:
            hnsw_kwargs["full_scan_threshold"] = int(plan.spec.hnsw_full_scan_threshold)
        optimizer = None
        if plan.spec.indexing_threshold is not None:
            optimizer = models.OptimizersConfigDiff(
                indexing_threshold=int(plan.spec.indexing_threshold)
            )
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=plan.spec.dim, distance=distance),
            hnsw_config=models.HnswConfigDiff(**hnsw_kwargs),
            optimizers_config=optimizer,
        )
        tenant_field = plan.spec.tenant_field
        id_to_tenant = (
            {
                int(vid): plan.tenant_of[i]
                for i, vid in enumerate(plan.corpus.ids.tolist())
            }
            if plan.tenant_of
            else {}
        )
        points = [
            models.PointStruct(
                id=int(vid),
                vector=plan.corpus.vectors[i].tolist(),
                payload=(
                    {tenant_field: id_to_tenant[int(vid)]} if id_to_tenant else None
                ),
            )
            for i, vid in enumerate(plan.corpus.ids.tolist())
        ]
        client.upsert(collection_name=name, points=points, wait=True)
        if plan.deleted_ids:
            client.delete(
                collection_name=name, points_selector=list(plan.deleted_ids), wait=True
            )
        if plan.updated_ids:
            updates = [
                models.PointStruct(
                    id=int(vid),
                    vector=plan.update_vectors[i].tolist(),
                    payload=(
                        {tenant_field: id_to_tenant[int(vid)]} if id_to_tenant else None
                    ),
                )
                for i, vid in enumerate(plan.updated_ids)
            ]
            client.upsert(collection_name=name, points=updates, wait=True)
        if plan.spec.n_tenants > 0:
            client.create_payload_index(
                collection_name=name,
                field_name=tenant_field,
                field_schema=models.KeywordIndexParams(
                    type="keyword",
                    is_tenant=True,
                ),
                wait=True,
            )
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()


def apply_lancedb(path: str | Path, plan: SeedPlan) -> None:
    """Write a Lance dataset with the same corpus and deletion set as ``plan``."""
    require_optional_import("lance", extra="lancedb")
    require_optional_import("pyarrow", extra="lancedb")
    import lance
    import pyarrow as pa

    dim = int(plan.spec.dim)
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), dim)),
        ]
    )
    table = pa.Table.from_arrays(
        [
            pa.array([int(i) for i in plan.corpus.ids.tolist()]),
            pa.array(
                plan.corpus.vectors.tolist(),
                type=pa.list_(pa.float32(), dim),
            ),
        ],
        schema=schema,
    )
    dest = str(path)
    lance.write_dataset(table, dest)
    ds = lance.dataset(dest)
    if plan.deleted_ids:
        id_list = ", ".join(str(int(i)) for i in plan.deleted_ids)
        ds.delete(f"id IN ({id_list})")
    metric = {
        MetricSpace.COSINE: "cosine",
        MetricSpace.L2: "L2",
        MetricSpace.DOT: "dot",
    }[plan.spec.metric_space]
    n_live = plan.spec.n - plan.spec.n_delete
    n_parts = max(2, min(8, n_live // 64))
    ds.create_index(
        column="vector",
        index_type="IVF_FLAT",
        metric_type=metric,
        num_partitions=n_parts,
    )


def apply_postgres(service: PostgresService, plan: SeedPlan) -> None:
    """Create a table + HNSW index, insert the corpus, then apply churn."""
    require_optional_import("psycopg", extra="postgres")
    require_optional_import("pgvector", extra="postgres")
    import psycopg
    from pgvector.psycopg import register_vector

    table = quote_ident(plan.spec.name)
    opclass = _PG_OPCLASS[plan.spec.metric_space]
    dim = int(plan.spec.dim)
    m = int(plan.spec.m)
    ef = int(plan.spec.ef_construction)
    index_name = quote_ident(f"{plan.spec.name}_hnsw")

    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        conn.execute(
            f"CREATE TABLE {table} (id bigint PRIMARY KEY, embedding vector({dim}))"
        )
        if not plan.spec.autovacuum:
            conn.execute(f"ALTER TABLE {table} SET (autovacuum_enabled = false)")
        rows = [
            (int(vid), plan.corpus.vectors[i])
            for i, vid in enumerate(plan.corpus.ids.tolist())
        ]
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {table} (id, embedding) VALUES (%s, %s)",
                rows,
            )
        conn.execute(
            f"CREATE INDEX {index_name} ON {table} "
            f"USING hnsw (embedding {opclass}) "
            f"WITH (m = {m}, ef_construction = {ef})"
        )
        if plan.deleted_ids:
            conn.execute(
                f"DELETE FROM {table} WHERE id = ANY(%s)",
                (list(plan.deleted_ids),),
            )
        if plan.updated_ids:
            with conn.cursor() as cur:
                cur.executemany(
                    f"UPDATE {table} SET embedding = %s WHERE id = %s",
                    [
                        (plan.update_vectors[i], int(vid))
                        for i, vid in enumerate(plan.updated_ids)
                    ],
                )
    finally:
        conn.close()


def postgres_prepare_repro_db(service: PostgresService) -> None:
    """Force the extra-container planner onto HNSW (P7-04 seq-scan trap).

    At a few thousand 16-d rows the planner still prefers a sequential scan.
    ``enable_seqscan=off`` is a harness knob on this throwaway database only.
    """
    require_optional_import("psycopg", extra="postgres")
    import psycopg

    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute("ALTER DATABASE test SET enable_seqscan = off")
    finally:
        conn.close()


def postgres_analyze(service: PostgresService, table: str) -> None:
    """Refresh table stats so ``n_dead_tup`` is visible. Harness-only."""
    require_optional_import("psycopg", extra="postgres")
    import psycopg

    ident = quote_ident(table)
    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute(f"ANALYZE {ident}")
    finally:
        conn.close()


def postgres_vacuum(service: PostgresService, table: str) -> None:
    """Operator VACUUM (not vhecfsck). Reclaims dead tuples from heap + HNSW."""
    require_optional_import("psycopg", extra="postgres")
    import psycopg

    ident = quote_ident(table)
    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute(f"VACUUM {ident}")
    finally:
        conn.close()


def postgres_extra_update_rounds(
    service: PostgresService, plan: SeedPlan, *, rounds: int
) -> None:
    """Repeat UPDATEs on live rows to pile dead tuples with autovacuum off."""
    if rounds < 1:
        return
    require_optional_import("psycopg", extra="postgres")
    require_optional_import("pgvector", extra="postgres")
    import psycopg
    from pgvector.psycopg import register_vector

    ident = quote_ident(plan.spec.name)
    live = [
        int(vid)
        for vid in plan.corpus.ids.tolist()
        if int(vid) not in set(plan.deleted_ids)
    ]
    if not live:
        return
    rng = np.random.default_rng(plan.spec.seed + 7)
    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        dim = int(plan.spec.dim)
        with conn.cursor() as cur:
            for _ in range(rounds):
                vecs = rng.standard_normal((len(live), dim), dtype=np.float32)
                cur.executemany(
                    f"UPDATE {ident} SET embedding = %s WHERE id = %s",
                    [(vecs[i], live[i]) for i in range(len(live))],
                )
    finally:
        conn.close()


def postgres_raw_knn(
    service: PostgresService,
    *,
    table: str,
    queries: NDArray[np.float32],
    k: int,
    metric_space: MetricSpace,
    ef_search: int,
    iterative_scan: str = "off",
) -> NDArray[np.int64]:
    """HNSW k-NN via SQL (no vhecfsck). Pads short rows with -1."""
    require_optional_import("psycopg", extra="postgres")
    require_optional_import("pgvector", extra="postgres")
    import psycopg
    from pgvector.psycopg import register_vector

    ident = quote_ident(table)
    op = _PG_OPS[metric_space]
    qn = int(queries.shape[0])
    out = np.full((qn, k), -1, dtype=np.int64)
    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        conn.execute(
            "SELECT set_config('hnsw.ef_search', %s, false)",
            (str(ef_search),),
        )
        conn.execute(
            "SELECT set_config('hnsw.iterative_scan', %s, false)", (iterative_scan,)
        )
        sql = f"SELECT id FROM {ident} ORDER BY embedding {op} %s LIMIT %s"
        with conn.cursor() as cur:
            for qi in range(qn):
                cur.execute(sql, (queries[qi], k))
                rows = cur.fetchall()
                for hi, row in enumerate(rows[:k]):
                    out[qi, hi] = int(row[0])
    finally:
        conn.close()
    return out


def postgres_explain_uses_hnsw(
    service: PostgresService,
    *,
    table: str,
    query: NDArray[np.float32],
    k: int,
    metric_space: MetricSpace,
) -> bool:
    """True when EXPLAIN JSON for a k-NN query contains an index scan node."""
    require_optional_import("psycopg", extra="postgres")
    require_optional_import("pgvector", extra="postgres")
    import psycopg
    from pgvector.psycopg import register_vector
    from vhecfsck.adapters.postgres_adapter import plan_uses_index

    ident = quote_ident(table)
    op = _PG_OPS[metric_space]
    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        sql = (
            f"EXPLAIN (FORMAT JSON) SELECT id FROM {ident} "
            f"ORDER BY embedding {op} %s LIMIT %s"
        )
        with conn.cursor() as cur:
            cur.execute(sql, (query, k))
            plan = cur.fetchone()[0]
        return bool(plan_uses_index(plan))
    finally:
        conn.close()


def _embedding_to_array(raw: object) -> np.ndarray:
    to_numpy = getattr(raw, "to_numpy", None)
    if callable(to_numpy):
        return np.asarray(to_numpy(), dtype=np.float32)
    to_list = getattr(raw, "to_list", None)
    if callable(to_list):
        return np.asarray(to_list(), dtype=np.float32)
    return np.asarray(raw, dtype=np.float32)


def postgres_fetch_live(
    service: PostgresService, table: str
) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
    """Read live heap rows (id, embedding) for independent recall."""
    require_optional_import("psycopg", extra="postgres")
    require_optional_import("pgvector", extra="postgres")
    import psycopg
    from pgvector.psycopg import register_vector

    ident = quote_ident(table)
    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, embedding FROM {ident} ORDER BY id")
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return np.empty(0, dtype=np.int64), np.empty((0, 0), dtype=np.float32)
    ids = np.ascontiguousarray(np.array([int(r[0]) for r in rows], dtype=np.int64))
    converted = [_embedding_to_array(row[1]) for row in rows]
    vecs = np.ascontiguousarray(np.stack(converted, axis=0).astype(np.float32))
    return ids, vecs


def postgres_dead_tuple_counts(service: PostgresService, table: str) -> tuple[int, int]:
    """``(n_live_tup, n_dead_tup)`` from ``pg_stat_user_tables``."""
    require_optional_import("psycopg", extra="postgres")
    import psycopg

    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT n_live_tup, n_dead_tup FROM pg_catalog.pg_stat_user_tables "
                "WHERE relname = %s",
                (table,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)


def postgres_server_healthy(service: PostgresService) -> bool:
    """True when the throwaway server answers ``SELECT 1``."""
    require_optional_import("psycopg", extra="postgres")
    import psycopg

    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
        return row is not None and int(row[0]) == 1
    finally:
        conn.close()


def qdrant_http_ok(service: QdrantService) -> bool:
    """True when ``GET /healthz`` returns 2xx."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{service.http_url}/healthz", timeout=5) as resp:
            return 200 <= int(resp.status) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def qdrant_wait_green(
    service: QdrantService, collection: str, *, timeout_s: float = 60.0
) -> bool:
    """Poll collection status until green or timeout."""
    import time

    require_optional_import("qdrant_client", extra="qdrant")
    from qdrant_client import QdrantClient

    client = QdrantClient(host=service.host, port=service.http_port, prefer_grpc=False)
    try:
        deadline = time.monotonic() + float(timeout_s)
        while time.monotonic() < deadline:
            info = client.get_collection(collection)
            status = str(getattr(info, "status", "")).lower()
            if "green" in status:
                return True
            time.sleep(0.2)
        return False
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()


def qdrant_knn_ids(
    service: QdrantService,
    collection: str,
    vector: NDArray[np.floating],
    k: int,
    *,
    tenant_field: str | None = None,
    tenant_value: object | None = None,
    ef_search: int = 64,
) -> list[int]:
    """Raw ``query_points`` ids, independent of ``vhecfsck`` (harness only)."""
    require_optional_import("qdrant_client", extra="qdrant")
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    query_filter = None
    if tenant_field is not None and tenant_value is not None:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key=tenant_field,
                    match=models.MatchValue(value=tenant_value),
                )
            ]
        )
    client = QdrantClient(host=service.host, port=service.http_port, prefer_grpc=False)
    try:
        result = client.query_points(
            collection_name=collection,
            query=np.asarray(vector, dtype=np.float32).tolist(),
            limit=int(k),
            query_filter=query_filter,
            search_params=models.SearchParams(hnsw_ef=int(ef_search)),
            with_payload=False,
            with_vectors=False,
        )
        points = getattr(result, "points", result)
        return [int(p.id) for p in list(points or [])]
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()


def qdrant_churn_upsert(
    service: QdrantService,
    plan: SeedPlan,
    *,
    rounds: int,
) -> None:
    """Re-upsert live points to encourage segment merge (harness write path)."""
    require_optional_import("qdrant_client", extra="qdrant")
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    if rounds < 1:
        return
    name = plan.spec.name
    live = {int(i) for i in plan.corpus.ids.tolist()} - set(plan.deleted_ids)
    tenant_field = plan.spec.tenant_field
    id_to_tenant = (
        {int(vid): plan.tenant_of[i] for i, vid in enumerate(plan.corpus.ids.tolist())}
        if plan.tenant_of
        else {}
    )
    points = [
        models.PointStruct(
            id=int(vid),
            vector=plan.corpus.vectors[i].tolist(),
            payload=({tenant_field: id_to_tenant[int(vid)]} if id_to_tenant else None),
        )
        for i, vid in enumerate(plan.corpus.ids.tolist())
        if int(vid) in live
    ]
    client = QdrantClient(host=service.host, port=service.http_port, prefer_grpc=False)
    try:
        for _ in range(int(rounds)):
            client.upsert(collection_name=name, points=points, wait=True)
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()
