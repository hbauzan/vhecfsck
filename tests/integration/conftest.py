"""Shared helpers for engine integration tests (P7).

Write-side seeding lives here, outside ``vhecfsck/``, so the package never
gains a mutation path (ADR-0001).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import numpy as np
import pytest
from tests.integration.containers import (
    invocation_is_integration_dir,
    postgres_container_session,
    qdrant_container_session,
)


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


@pytest.fixture(scope="session")
def qdrant_service() -> Iterator[object]:
    """Session-scoped Qdrant container (P7-01)."""
    with qdrant_container_session() as service:
        yield service


@pytest.fixture(scope="session")
def postgres_service() -> Iterator[object]:
    """Session-scoped PostgreSQL+pgvector container (P7-01).

    Also exports ``VHECFSCK_POSTGRES_DSN`` so existing DSN-gated tests in this
    directory run against the throwaway server instead of skipping.
    """
    with postgres_container_session() as service:
        previous = os.environ.get("VHECFSCK_POSTGRES_DSN")
        os.environ["VHECFSCK_POSTGRES_DSN"] = service.dsn
        try:
            yield service
        finally:
            if previous is None:
                os.environ.pop("VHECFSCK_POSTGRES_DSN", None)
            else:
                os.environ["VHECFSCK_POSTGRES_DSN"] = previous


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Re-enable ``integration`` tests when the invocation is that directory.

    Default addopts include ``not integration``. ``pytest tests/integration``
    is the documented on-demand command and must not deselect the harness.
    """
    del items
    if not invocation_is_integration_dir(config):
        return
    expr = (config.option.markexpr or "").strip()
    if "not integration" not in expr:
        return
    rewritten = (
        expr.replace("and not integration", "")
        .replace("not integration and", "")
        .replace("not integration", "")
        .strip()
    )
    config.option.markexpr = rewritten
