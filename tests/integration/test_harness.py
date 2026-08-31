# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""P7-01: live container reachability, teardown, and deterministic seeding."""

from __future__ import annotations

import socket
from urllib.request import urlopen

import pytest
from tests.integration.containers import (
    PostgresService,
    QdrantService,
    require_optional_import,
)
from tests.integration.seeding import (
    SeedSpec,
    apply_postgres,
    apply_qdrant,
    build_seed_plan,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_docker,
]


def test_qdrant_container_is_ready(qdrant_service: QdrantService) -> None:
    with urlopen(f"{qdrant_service.http_url}/readyz", timeout=5) as resp:
        assert resp.status == 200


def test_postgres_container_accepts_tcp(postgres_service: PostgresService) -> None:
    with socket.create_connection(
        (postgres_service.host, postgres_service.port), timeout=5
    ) as sock:
        assert sock.getpeername()[1] == postgres_service.port


def test_both_containers_are_reachable_together(
    qdrant_service: QdrantService, postgres_service: PostgresService
) -> None:
    with urlopen(f"{qdrant_service.http_url}/readyz", timeout=5) as resp:
        assert resp.status == 200
    with socket.create_connection(
        (postgres_service.host, postgres_service.port), timeout=5
    ):
        pass


def test_qdrant_seeding_is_deterministic(qdrant_service: QdrantService) -> None:
    require_optional_import("qdrant_client", extra="qdrant")
    from qdrant_client import QdrantClient

    spec_a = SeedSpec(name="q_det_a", seed=7, n=24, dim=8, n_delete=4)
    spec_b = SeedSpec(name="q_det_b", seed=7, n=24, dim=8, n_delete=4)
    plan_a = build_seed_plan(spec_a)
    plan_b = build_seed_plan(spec_b)
    assert (plan_a.corpus.vectors == plan_b.corpus.vectors).all()
    apply_qdrant(qdrant_service, plan_a)
    apply_qdrant(qdrant_service, plan_b)
    client = QdrantClient(
        host=qdrant_service.host, port=qdrant_service.http_port, prefer_grpc=False
    )
    try:
        count_a = int(client.count("q_det_a", exact=True).count)
        count_b = int(client.count("q_det_b", exact=True).count)
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()
    expected = spec_a.n - spec_a.n_delete
    assert count_a == count_b == expected


def test_postgres_seeding_is_deterministic(postgres_service: PostgresService) -> None:
    require_optional_import("psycopg", extra="postgres")
    require_optional_import("pgvector", extra="postgres")
    import psycopg
    from pgvector.psycopg import register_vector

    spec_a = SeedSpec(name="pg_det_a", seed=7, n=24, dim=8, n_delete=4)
    spec_b = SeedSpec(name="pg_det_b", seed=7, n=24, dim=8, n_delete=4)
    plan_a = build_seed_plan(spec_a)
    plan_b = build_seed_plan(spec_b)
    assert (plan_a.corpus.vectors == plan_b.corpus.vectors).all()
    apply_postgres(postgres_service, plan_a)
    apply_postgres(postgres_service, plan_b)
    conn = psycopg.connect(postgres_service.dsn, autocommit=True)
    try:
        register_vector(conn)
        count_a = conn.execute("SELECT count(*) FROM pg_det_a").fetchone()[0]
        count_b = conn.execute("SELECT count(*) FROM pg_det_b").fetchone()[0]
    finally:
        conn.close()
    expected = spec_a.n - spec_a.n_delete
    assert int(count_a) == int(count_b) == expected
