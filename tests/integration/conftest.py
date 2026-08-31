"""Shared helpers for engine integration tests (P7).

Write-side seeding lives here, outside ``vhecfsck/``, so the package never
gains a mutation path (ADR-0001).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import numpy as np
import pytest


def postgres_dsn() -> str | None:
    """Return ``VHECFSCK_POSTGRES_DSN`` when a live server is configured."""
    raw = os.environ.get("VHECFSCK_POSTGRES_DSN", "").strip()
    return raw or None


@pytest.fixture
def require_qdrant_extra() -> None:
    pytest.importorskip("qdrant_client")


@pytest.fixture
def require_postgres_extra() -> None:
    pytest.importorskip("psycopg")
    pytest.importorskip("pgvector")


@pytest.fixture
def qdrant_embedded_collection() -> Iterator[tuple[object, str]]:
    """Seed an in-memory Qdrant collection; yield ``(client, name)``."""
    qdrant_client = pytest.importorskip("qdrant_client")
    models = pytest.importorskip("qdrant_client.http.models")
    client = qdrant_client.QdrantClient(":memory:")
    name = "audit_col"
    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=8, distance=models.Distance.COSINE),
    )
    rng = np.random.default_rng(42)
    vectors = rng.normal(size=(24, 8)).astype(np.float32)
    points = [
        models.PointStruct(
            id=i,
            vector=vectors[i].tolist(),
            payload={"i": i},
        )
        for i in range(24)
    ]
    client.upsert(collection_name=name, points=points)
    try:
        yield client, name
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()
