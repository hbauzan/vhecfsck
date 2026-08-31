# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""Deterministic corpus + index + churn seeding for Qdrant and pgvector.

Lives under ``tests/`` so write APIs never enter ``vhecfsck/`` (ADR-0001).
Both engines consume the same ``SeedPlan`` so later cross-engine tests share
one corpus, one index shape, and one churn pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class SeedPlan:
    """Arrays plus the spec that produced them — byte-identical at a fixed seed."""

    spec: SeedSpec
    corpus: GeneratedCorpus
    deleted_ids: tuple[int, ...]
    updated_ids: tuple[int, ...]
    update_vectors: NDArray[np.float32]


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
    if spec.m < 2 or spec.ef_construction < 1:
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
    return SeedPlan(
        spec=spec,
        corpus=corpus,
        deleted_ids=deleted_ids,
        updated_ids=updated_ids,
        update_vectors=update_vectors,
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
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=plan.spec.dim, distance=distance),
            hnsw_config=models.HnswConfigDiff(
                m=plan.spec.m, ef_construct=plan.spec.ef_construction
            ),
        )
        points = [
            models.PointStruct(
                id=int(vid),
                vector=plan.corpus.vectors[i].tolist(),
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
                )
                for i, vid in enumerate(plan.updated_ids)
            ]
            client.upsert(collection_name=name, points=updates, wait=True)
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()


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
