# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""Reproduce pgvector#244: dead tuples collapse HNSW recall (P7-05).

Pathology is seeded in this harness (ADR-0001). ``vhecfsck`` never VACUUMs.
"""

from __future__ import annotations

import numpy as np
import pytest
from tests.integration.containers import PostgresService
from tests.integration.seeding import (
    SeedSpec,
    apply_postgres,
    build_seed_plan,
    postgres_analyze,
    postgres_dead_tuple_counts,
    postgres_explain_uses_hnsw,
    postgres_extra_update_rounds,
    postgres_fetch_live,
    postgres_prepare_repro_db,
    postgres_raw_knn,
    postgres_server_healthy,
    postgres_vacuum,
)
from vhecfsck.adapters.postgres_adapter import PostgresAdapter
from vhecfsck.config import AuditConfig
from vhecfsck.core.verdict import verdict_to_exit_code
from vhecfsck.models import MetricSpace, MetricState, Verdict
from vhecfsck.models.report import metric_by_id
from vhecfsck.pipeline import run_audit

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

_TABLE = "pg244"
_N = 2500
_DIM = 16
_K = 10
_EF = 10
_Q = 40
_SEED = 244
_UPDATE_ROUNDS = 6


def _enabled() -> dict[str, bool]:
    return {
        "canary_recall": True,
        "hub_share_top1pct": False,
        "antihub_fraction": False,
        "dfi": True,
        "partition_size_cv": False,
    }


def _brute_knn_selfex(
    queries: np.ndarray,
    query_ids: np.ndarray,
    corpus_ids: np.ndarray,
    corpus_vecs: np.ndarray,
    k: int,
) -> np.ndarray:
    qn = int(queries.shape[0])
    out = np.full((qn, k), -1, dtype=np.int64)
    ids = corpus_ids.astype(np.int64, copy=False)
    for qi in range(qn):
        exclude = int(query_ids[qi])
        diff = corpus_vecs.astype(np.float64, copy=False) - queries[qi].astype(
            np.float64, copy=False
        )
        dist = np.sqrt((diff * diff).sum(axis=1))
        order = np.lexsort((ids, dist))
        taken: list[int] = []
        for j in order:
            vid = int(ids[j])
            if vid == exclude:
                continue
            taken.append(vid)
            if len(taken) >= k:
                break
        out[qi, : len(taken)] = taken
    return out


def _id_recall_and_shorts(
    returned: np.ndarray,
    truth: np.ndarray,
    k: int,
    query_ids: np.ndarray | None = None,
) -> tuple[float, int, int]:
    """Mean ID-set recall, short-row count, empty-row count (self excluded)."""
    qn = int(returned.shape[0])
    hits = 0.0
    shorts = 0
    empties = 0
    for qi in range(qn):
        exclude = int(query_ids[qi]) if query_ids is not None else None
        got = [
            int(x) for x in returned[qi].tolist() if int(x) >= 0 and int(x) != exclude
        ]
        if len(got) < k:
            shorts += 1
        if not got:
            empties += 1
        gt = {int(x) for x in truth[qi].tolist() if int(x) >= 0}
        hits += len(gt.intersection(got)) / float(k)
    return hits / float(qn), shorts, empties


def _audit(dsn: str) -> object:
    adapter = PostgresAdapter(f"{dsn}?table={_TABLE}&column=embedding&id_column=id")
    try:
        cfg = AuditConfig(
            seed=_SEED,
            queries=_Q,
            k=_K,
            hubness_sample_size=1000,
            metrics_enabled=_enabled(),
        )
        return run_audit(adapter, cfg, search_params={"ef_search": _EF})
    finally:
        adapter.close()


def test_reproduce_pgvector_244_dead_tuple_recall_collapse(
    postgres_repro_service: PostgresService,
) -> None:
    postgres_prepare_repro_db(postgres_repro_service)
    spec = SeedSpec(
        n=_N,
        dim=_DIM,
        seed=_SEED,
        metric_space=MetricSpace.L2,
        m=16,
        ef_construction=64,
        n_delete=500,
        n_update=2000,
        n_clusters=8,
        name=_TABLE,
        autovacuum=False,
    )
    plan = build_seed_plan(spec)
    apply_postgres(postgres_repro_service, plan)
    postgres_extra_update_rounds(postgres_repro_service, plan, rounds=_UPDATE_ROUNDS)
    postgres_analyze(postgres_repro_service, _TABLE)

    assert postgres_server_healthy(postgres_repro_service)

    live_ids, live_vecs = postgres_fetch_live(postgres_repro_service, _TABLE)
    assert int(live_ids.shape[0]) == _N - spec.n_delete
    probe = live_vecs[:_Q]
    probe_ids = live_ids[:_Q]
    assert postgres_explain_uses_hnsw(
        postgres_repro_service,
        table=_TABLE,
        query=probe[0],
        k=_K,
        metric_space=MetricSpace.L2,
    ), "planner must use HNSW (table too small → seq scan, not this pathology)"

    truth = _brute_knn_selfex(probe, probe_ids, live_ids, live_vecs, _K)

    raw_off = postgres_raw_knn(
        postgres_repro_service,
        table=_TABLE,
        queries=probe,
        k=_K,
        metric_space=MetricSpace.L2,
        ef_search=_EF,
        iterative_scan="off",
    )
    recall_off, shorts_off, empty_off = _id_recall_and_shorts(
        raw_off, truth, _K, probe_ids
    )

    raw_on = postgres_raw_knn(
        postgres_repro_service,
        table=_TABLE,
        queries=probe,
        k=_K,
        metric_space=MetricSpace.L2,
        ef_search=_EF,
        iterative_scan="relaxed_order",
    )
    recall_on, shorts_on, empty_on = _id_recall_and_shorts(raw_on, truth, _K, probe_ids)

    live_stat, dead_stat = postgres_dead_tuple_counts(postgres_repro_service, _TABLE)
    print(
        "pgvector#244 independent "
        f"recall_off={recall_off:.4f} shorts_off={shorts_off} empty_off={empty_off} "
        f"recall_on={recall_on:.4f} shorts_on={shorts_on} empty_on={empty_on} "
        f"n_live_tup={live_stat} n_dead_tup={dead_stat}"
    )

    reproducing = recall_off < 0.70 and (shorts_off > 0 or empty_off > 0)
    if not reproducing and recall_on < 0.70 and (shorts_on > 0 or empty_on > 0):
        pytest.fail(
            "iterative_scan=off did not reproduce; on did. Pin off in the harness. "
            f"Measured off={recall_off:.4f}/{shorts_off} on={recall_on:.4f}/{shorts_on}"
        )
    assert reproducing, (
        "pgvector#244 did not reproduce with iterative_scan=off "
        f"(recall={recall_off:.4f}, shorts={shorts_off}, empty={empty_off}, "
        f"on={recall_on:.4f}/{shorts_on}). Server was healthy."
    )
    assert recall_on > recall_off, (
        "iterative_scan=relaxed_order should mitigate vs off: "
        f"off={recall_off:.4f} on={recall_on:.4f}"
    )

    report_before = _audit(postgres_repro_service.dsn)
    canary = metric_by_id(report_before, "canary_recall")
    dfi = metric_by_id(report_before, "dfi")
    assert canary is not None and dfi is not None
    print(
        "pgvector#244 vhecfsck before VACUUM "
        f"canary={canary.value} state={canary.state.value} "
        f"returned_invalid={canary.detail.get('returned_invalid')} "
        f"short_returns={canary.detail.get('short_returns')} "
        f"dfi={dfi.value} dfi_state={dfi.state.value} "
        f"verdict={report_before.verdict.value} "
        f"unavailable={canary.unavailable_reason}"
    )

    assert canary.state is MetricState.FAIL
    assert canary.value is not None and float(canary.value) < 0.70
    assert int(canary.detail["short_returns"]) > 0
    # Heap visibility filters dead tids: the engine never returns a deleted id.
    # Measured returned_invalid=0. The #244 smoking gun is short/empty returns.
    assert int(canary.detail["returned_invalid"]) == 0
    assert dfi.value is not None and float(dfi.value) > 0.15
    assert report_before.verdict is Verdict.FAIL
    assert verdict_to_exit_code(report_before.verdict) == 2

    postgres_vacuum(postgres_repro_service, _TABLE)
    postgres_analyze(postgres_repro_service, _TABLE)

    live_ids_a, live_vecs_a = postgres_fetch_live(postgres_repro_service, _TABLE)
    truth_after = _brute_knn_selfex(probe, probe_ids, live_ids_a, live_vecs_a, _K)
    raw_after = postgres_raw_knn(
        postgres_repro_service,
        table=_TABLE,
        queries=probe,
        k=_K,
        metric_space=MetricSpace.L2,
        ef_search=_EF,
        iterative_scan="off",
    )
    recall_after, shorts_after, empty_after = _id_recall_and_shorts(
        raw_after, truth_after, _K, probe_ids
    )
    live_after, dead_after = postgres_dead_tuple_counts(postgres_repro_service, _TABLE)
    print(
        "pgvector#244 after VACUUM "
        f"recall={recall_after:.4f} shorts={shorts_after} empty={empty_after} "
        f"n_live_tup={live_after} n_dead_tup={dead_after}"
    )

    report_after = _audit(postgres_repro_service.dsn)
    canary_a = metric_by_id(report_after, "canary_recall")
    dfi_a = metric_by_id(report_after, "dfi")
    assert canary_a is not None and dfi_a is not None
    print(
        "pgvector#244 vhecfsck after VACUUM "
        f"canary={canary_a.value} state={canary_a.state.value} "
        f"returned_invalid={canary_a.detail.get('returned_invalid')} "
        f"short_returns={canary_a.detail.get('short_returns')} "
        f"dfi={dfi_a.value}"
    )

    assert canary_a.value is not None
    assert float(canary_a.value) > float(canary.value)
    assert dfi_a.value is not None
    assert float(dfi_a.value) < float(dfi.value)
    assert recall_after > recall_off
    assert empty_after < empty_off
    assert dead_after < dead_stat
    assert postgres_server_healthy(postgres_repro_service)
