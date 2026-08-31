"""Integration tests for HNSW graph statistics availability (P7-06)."""

from __future__ import annotations

import pytest
from vhecfsck.adapters.postgres_adapter import PostgresAdapter
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter

pytestmark = pytest.mark.integration


def test_qdrant_graph_stats_returns_none_and_capability_false(
    qdrant_embedded_collection: tuple[object, str],
) -> None:
    """Qdrant embedded/container graph_stats is None & capability False."""
    client, name = qdrant_embedded_collection
    adapter = QdrantAdapter(f"qdrant://memory/{name}", client=client)
    try:
        assert adapter.capabilities.report_graph_stats is False
        assert adapter.graph_stats() is None
    finally:
        adapter.close()


def test_postgres_graph_stats_returns_none_and_capability_false(
    postgres_service: str,
) -> None:
    """Postgres container server graph_stats is None & capability False."""
    # postgres_service is a DSN string provided by testcontainers fixture
    adapter = PostgresAdapter(
        f"{postgres_service}?table=test_table&column=embedding&id_column=id"
    )
    try:
        assert adapter.capabilities.report_graph_stats is False
        assert adapter.graph_stats() is None
    finally:
        adapter.close()
