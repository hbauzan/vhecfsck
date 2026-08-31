"""Integration tests for HNSW graph statistics availability (P7-06)."""

from __future__ import annotations

import pytest
from tests.integration.containers import PostgresService
from tests.integration.seeding import SeedSpec, apply_postgres, build_seed_plan
from vhecfsck.adapters.postgres_adapter import PostgresAdapter
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


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
    postgres_service: PostgresService,
) -> None:
    """Postgres container server graph_stats is None & capability False."""
    spec = SeedSpec(name="graph_stats_pg", n=8, dim=4, n_delete=0)
    apply_postgres(postgres_service, build_seed_plan(spec))
    adapter = PostgresAdapter(
        f"{postgres_service.dsn}?table=graph_stats_pg&column=embedding&id_column=id"
    )
    try:
        assert adapter.capabilities.report_graph_stats is False
        assert adapter.graph_stats() is None
    finally:
        adapter.close()
