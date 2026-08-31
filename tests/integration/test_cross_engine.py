# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""P7-07: same corpus, four engines — hubness agrees; recall/DFI in range."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from tests.integration.containers import PostgresService, QdrantService
from tests.integration.seeding import (
    SeedSpec,
    apply_lancedb,
    apply_postgres,
    apply_qdrant,
    build_seed_plan,
)
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter
from vhecfsck.adapters.postgres_adapter import PostgresAdapter, quote_ident
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter
from vhecfsck.adapters.synthetic_adapter import SyntheticAdapter
from vhecfsck.config import AuditConfig
from vhecfsck.models import MetricSpace, MetricState
from vhecfsck.models.metrics import MetricResult
from vhecfsck.models.report import metric_by_id
from vhecfsck.pipeline import run_audit
from vhecfsck.synthetic.pathologies import (
    GroundTruthAnnotation,
    corpus_state_from_generated,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

_NAME = "cross_engine"
_HUB_TOL = 0.02
_SEARCH = {"ef_search": 64, "nprobe": 8}


def _spec() -> SeedSpec:
    return SeedSpec(
        n=1024,
        dim=16,
        seed=2026,
        metric_space=MetricSpace.L2,
        m=16,
        ef_construction=64,
        n_delete=16,
        n_update=0,
        n_clusters=4,
        name=_NAME,
    )


def _config() -> AuditConfig:
    return AuditConfig(
        seed=2026,
        queries=40,
        k=10,
        hubness_sample_size=2048,
        metrics_enabled={
            "canary_recall": True,
            "hub_share_top1pct": True,
            "antihub_fraction": True,
            "dfi": True,
            "partition_size_cv": False,
        },
    )


def _value(metric: MetricResult | None) -> float | None:
    if metric is None or metric.state is MetricState.UNAVAILABLE:
        return None
    return metric.value


def _drop_qdrant(service: QdrantService, name: str) -> None:
    from qdrant_client import QdrantClient

    client = QdrantClient(host=service.host, port=service.http_port, prefer_grpc=False)
    try:
        exists = getattr(client, "collection_exists", None)
        if callable(exists) and exists(name):
            client.delete_collection(name)
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()


def _drop_postgres(service: PostgresService, name: str) -> None:
    import psycopg

    table = quote_ident(name)
    conn = psycopg.connect(service.dsn, autocommit=True)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    finally:
        conn.close()


def _synthetic_adapter(plan: object) -> SyntheticAdapter:
    from tests.integration.seeding import SeedPlan

    assert isinstance(plan, SeedPlan)
    state = corpus_state_from_generated(plan.corpus)
    deleted = state.deleted.copy()
    dead = set(plan.deleted_ids)
    for i, vid in enumerate(state.ids.tolist()):
        if int(vid) in dead:
            deleted[i] = True
    n = int(state.ids.shape[0])
    n_del = int(deleted.sum())
    annotated = replace(
        state,
        deleted=deleted,
        annotation=GroundTruthAnnotation(
            dfi=(n_del / n) if n else 0.0,
            n_deleted=n_del,
            deleted_ids=plan.deleted_ids,
        ),
    )
    return SyntheticAdapter(annotated, mode="exact", index_name=_NAME)


def test_cross_engine_hubness_consistency(
    qdrant_service: QdrantService,
    postgres_service: PostgresService,
    tmp_path: Path,
    require_qdrant_extra: None,
    require_postgres_extra: None,
) -> None:
    """Hub share / anti-hub agree within 2%; recall and DFI stay in range."""
    del require_qdrant_extra, require_postgres_extra
    pytest.importorskip("lance")
    pytest.importorskip("pyarrow")

    plan = build_seed_plan(_spec())
    lance_dir = tmp_path / "cross.lance"
    apply_lancedb(lance_dir, plan)
    _drop_qdrant(qdrant_service, _NAME)
    apply_qdrant(qdrant_service, plan)
    _drop_postgres(postgres_service, _NAME)
    apply_postgres(postgres_service, plan)

    cfg = _config()
    adapters: dict[str, object] = {
        "synthetic": _synthetic_adapter(plan),
        "lancedb": LanceDBAdapter(str(lance_dir)),
        "qdrant": QdrantAdapter(
            f"qdrant://{qdrant_service.host}:{qdrant_service.http_port}/{_NAME}"
        ),
        "pgvector": PostgresAdapter(
            f"{postgres_service.dsn}?table={_NAME}&column=embedding"
        ),
    }
    rows: list[tuple[str, float | None, float | None, float | None, float | None]] = []
    try:
        for name, adapter in adapters.items():
            report = run_audit(adapter, cfg, search_params=_SEARCH)  # type: ignore[arg-type]
            hub = _value(metric_by_id(report, "hub_share_top1pct"))
            anti = _value(metric_by_id(report, "antihub_fraction"))
            rec = _value(metric_by_id(report, "canary_recall"))
            dfi = _value(metric_by_id(report, "dfi"))
            rows.append((name, hub, anti, rec, dfi))
            print(f"cross-engine {name}: hub={hub} anti={anti} recall={rec} dfi={dfi}")
    finally:
        for adapter in adapters.values():
            close = getattr(adapter, "close", None)
            if callable(close):
                close()

    print("| engine | hub_share | antihub | recall_dist | DFI |")
    print("| :--- | ---: | ---: | ---: | ---: |")
    for name, hub, anti, rec, dfi in rows:
        print(f"| {name} | {_fmt(hub)} | {_fmt(anti)} | {_fmt(rec)} | {_fmt(dfi)} |")

    hubs = [h for _, h, _, _, _ in rows if h is not None]
    antis = [a for _, _, a, _, _ in rows if a is not None]
    assert len(hubs) == 4
    assert len(antis) == 4
    assert max(hubs) - min(hubs) <= _HUB_TOL
    assert max(antis) - min(antis) <= _HUB_TOL

    recalls = [r for _, _, _, r, _ in rows if r is not None]
    assert recalls
    assert min(recalls) >= 0.70
    assert max(recalls) <= 1.0

    dfis = {name: dfi for name, _, _, _, dfi in rows}
    expected_dfi = 16 / 1024
    for engine in ("synthetic", "lancedb"):
        assert dfis[engine] is not None
        assert abs(float(dfis[engine]) - expected_dfi) < 1e-6
    if dfis["pgvector"] is not None:
        assert 0.0 <= float(dfis["pgvector"]) <= 0.30


def _fmt(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    return f"{value:.4f}"
