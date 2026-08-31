# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""P7-03: reproduce qdrant#7147 and the aggregate-vs-grouped canary contrast."""

from __future__ import annotations

import numpy as np
import pytest
from tests.integration.seeding import (
    SeedSpec,
    apply_qdrant,
    build_seed_plan,
    qdrant_churn_upsert,
    qdrant_http_ok,
    qdrant_knn_ids,
    qdrant_wait_green,
)
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter
from vhecfsck.config import AuditConfig
from vhecfsck.core.verdict import verdict_to_exit_code
from vhecfsck.models import MetricSpace, MetricState, Verdict
from vhecfsck.models.report import metric_by_id
from vhecfsck.pipeline import run_audit

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

_COLLECTION = "repro_qdrant_7147"
_TENANT_FIELD = "tenant_id"
_K = 10
_Q = 40
_EF = 64


def _recall_at_k(
    returned: list[int],
    gt: list[int],
    k: int,
    *,
    exclude: int | None,
) -> float:
    gt_set = {int(x) for x in gt if exclude is None or int(x) != int(exclude)}
    n_eff = min(k, len(gt_set))
    if n_eff <= 0:
        return 0.0
    hits = 0
    seen: set[int] = set()
    for rid in returned:
        ir = int(rid)
        if ir < 0 or ir == exclude or ir in seen:
            continue
        seen.add(ir)
        if ir in gt_set:
            hits += 1
        if len(seen) >= n_eff:
            break
    return hits / float(n_eff)


def _brute_knn(
    vectors: np.ndarray,
    ids: np.ndarray,
    query: np.ndarray,
    k: int,
    *,
    exclude: int | None,
) -> list[int]:
    q = np.asarray(query, dtype=np.float64)
    scored: list[tuple[float, int]] = []
    for i, vid in enumerate(ids.tolist()):
        iv = int(vid)
        if exclude is not None and iv == int(exclude):
            continue
        diff = vectors[i].astype(np.float64) - q
        scored.append((float(np.dot(diff, diff)), iv))
    scored.sort()
    return [vid for _, vid in scored[:k]]


def _metric_enabled() -> dict[str, bool]:
    return {
        "canary_recall": True,
        "hub_share_top1pct": False,
        "antihub_fraction": False,
        "dfi": True,
        "partition_size_cv": False,
    }


@pytest.fixture
def qdrant_7147_plan(qdrant_service: object, require_qdrant_extra: None) -> object:
    del require_qdrant_extra
    spec = SeedSpec(
        n=480,
        dim=16,
        seed=7147,
        metric_space=MetricSpace.COSINE,
        m=0,
        payload_m=32,
        ef_construction=64,
        n_delete=48,
        n_update=96,
        n_clusters=8,
        n_tenants=8,
        tenant_field=_TENANT_FIELD,
        name=_COLLECTION,
        indexing_threshold=10,
        hnsw_full_scan_threshold=10,
    )
    plan = build_seed_plan(spec)
    from qdrant_client import QdrantClient

    client = QdrantClient(
        host=qdrant_service.host,  # type: ignore[attr-defined]
        port=qdrant_service.http_port,  # type: ignore[attr-defined]
        prefer_grpc=False,
    )
    try:
        exists = getattr(client, "collection_exists", None)
        if callable(exists) and exists(_COLLECTION):
            client.delete_collection(_COLLECTION)
    finally:
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()
    apply_qdrant(qdrant_service, plan)  # type: ignore[arg-type]
    qdrant_churn_upsert(qdrant_service, plan, rounds=4)  # type: ignore[arg-type]
    assert qdrant_wait_green(qdrant_service, _COLLECTION, timeout_s=90)  # type: ignore[arg-type]
    return plan


def test_reproduce_qdrant_7147_filtered_canary(
    qdrant_service: object, qdrant_7147_plan: object
) -> None:
    """Independent pathology first, then aggregate-only vs grouped vhecfsck."""
    from tests.integration.containers import QdrantService
    from tests.integration.seeding import SeedPlan

    service = qdrant_service
    plan = qdrant_7147_plan
    assert isinstance(service, QdrantService)
    assert isinstance(plan, SeedPlan)

    assert qdrant_http_ok(service)
    assert qdrant_wait_green(service, _COLLECTION)

    live_mask = np.ones(plan.spec.n, dtype=bool)
    if plan.deleted_ids:
        deleted = set(plan.deleted_ids)
        live_mask = np.array(
            [int(vid) not in deleted for vid in plan.corpus.ids.tolist()]
        )
    live_ids = plan.corpus.ids[live_mask]
    live_vecs = plan.corpus.vectors[live_mask]
    live_tenants = np.array(plan.tenant_of, dtype=object)[live_mask]

    rng = np.random.default_rng(7147)
    take = min(_Q, int(live_ids.shape[0]))
    q_pos = rng.choice(live_ids.shape[0], size=take, replace=False)
    q_ids = live_ids[q_pos]
    q_vecs = live_vecs[q_pos]
    q_tenants = live_tenants[q_pos]

    unfiltered: list[float] = []
    filtered: list[float] = []
    empty_filtered = 0
    for i in range(take):
        qid = int(q_ids[i])
        tenant = str(q_tenants[i])
        raw_u = qdrant_knn_ids(
            service,
            _COLLECTION,
            q_vecs[i],
            _K + 1,
            ef_search=_EF,
        )
        gt_u = _brute_knn(live_vecs, live_ids, q_vecs[i], _K, exclude=qid)
        unfiltered.append(_recall_at_k(raw_u, gt_u, _K, exclude=qid))

        tenant_mask = live_tenants == tenant
        raw_f = qdrant_knn_ids(
            service,
            _COLLECTION,
            q_vecs[i],
            _K + 1,
            tenant_field=_TENANT_FIELD,
            tenant_value=tenant,
            ef_search=_EF,
        )
        if not raw_f:
            empty_filtered += 1
        gt_f = _brute_knn(
            live_vecs[tenant_mask],
            live_ids[tenant_mask],
            q_vecs[i],
            _K,
            exclude=qid,
        )
        filtered.append(_recall_at_k(raw_f, gt_f, _K, exclude=qid))

    mean_u = float(np.mean(unfiltered))
    mean_f = float(np.mean(filtered))
    min_f = float(np.min(filtered))
    print(
        f"qdrant#7147 independent: unfiltered={mean_u:.4f} "
        f"filtered_mean={mean_f:.4f} filtered_min={min_f:.4f} "
        f"empty_filtered={empty_filtered}/{take} healthz={qdrant_http_ok(service)}"
    )

    pathology = mean_u >= 0.80 and min_f < 0.70
    target = f"qdrant://{service.host}:{service.http_port}/{_COLLECTION}"
    adapter = QdrantAdapter(target)
    try:
        assert adapter.capabilities.filtered_search is True
        agg = run_audit(
            adapter,
            AuditConfig(
                seed=7147,
                queries=_Q,
                k=_K,
                hubness_sample_size=32,
                metrics_enabled=_metric_enabled(),
            ),
            search_params={"ef_search": _EF},
        )
        grouped = run_audit(
            adapter,
            AuditConfig(
                seed=7147,
                queries=_Q,
                k=_K,
                hubness_sample_size=32,
                metrics_enabled=_metric_enabled(),
                group_by=_TENANT_FIELD,
            ),
            search_params={"ef_search": _EF},
        )
    finally:
        adapter.close()

    agg_canary = metric_by_id(agg, "canary_recall")
    grouped_canary = metric_by_id(grouped, "canary_recall")
    assert agg_canary is not None
    assert grouped_canary is not None
    group_states = None
    if grouped.canary_groups is not None:
        group_states = {k: v.state.value for k, v in grouped.canary_groups.items()}
    print(
        f"vhecfsck aggregate canary={agg_canary.value} "
        f"state={agg_canary.state.value} verdict={agg.verdict.value}; "
        f"grouped verdict={grouped.verdict.value} groups={group_states}"
    )

    if pathology:
        assert agg_canary.state is not MetricState.FAIL
        assert agg.verdict is not Verdict.FAIL
        assert grouped.canary_groups is not None
        assert any(g.state is MetricState.FAIL for g in grouped.canary_groups.values())
        assert grouped.verdict is Verdict.FAIL
        assert verdict_to_exit_code(grouped.verdict) == 2
    else:
        # Pinned qdrant/qdrant:v1.19.0 did not reproduce the subgraph collapse.
        # Keep this as a regression guard: filtered precision must not crater
        # while the server stays green.
        assert mean_f >= 0.70
        assert empty_filtered == 0
        assert grouped.canary_groups is not None
        assert all(
            g.state is not MetricState.FAIL or g.evidence_strength.value == "low"
            for g in grouped.canary_groups.values()
        )
