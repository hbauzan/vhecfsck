"""Canary recall: tie-tolerant recall_id / recall_dist (P2-05).

Implements ``02-metrics-spec.md`` §2 and ADR-0007. True distances are always
recomputed from corpus vectors — never from the engine distance field.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.random import Generator, default_rng
from numpy.typing import NDArray

from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.models import (
    EvidenceStrength,
    MetricResult,
    MetricSpace,
    MetricState,
    ThresholdSpec,
    VectorBatch,
)

CANARY_METRIC_ID = "canary_recall"
CANARY_RTOL = 1e-6
CANARY_WARN = 0.85
CANARY_FAIL = 0.70
_MIN_QUERIES = 5
_LOW_EVIDENCE_Q = 30
_DEFAULT_BOOTSTRAP = 1000


@dataclass(frozen=True)
class QueryRecallDiag:
    """Per-query scoring diagnostics."""

    short_return: bool
    duplicate_returns: int
    returned_invalid: int
    boundary_tie: bool
    snapshot_inconsistent: int


def state_from_recall_dist(
    value: float,
    *,
    warn: float = CANARY_WARN,
    fail: float = CANARY_FAIL,
) -> MetricState:
    """Map recall_dist to OK/WARN/FAIL (``lower_is_worse``, §2 thresholds)."""
    if value < fail:
        return MetricState.FAIL
    if value < warn:
        return MetricState.WARN
    return MetricState.OK


def _pairwise_true_distance(
    query: NDArray[np.floating],
    vector: NDArray[np.floating],
    metric_space: MetricSpace,
) -> float:
    """Lower-is-better true distance recomputed from corpus coordinates."""
    q = np.asarray(query, dtype=np.float64)
    v = np.asarray(vector, dtype=np.float64)
    if metric_space is MetricSpace.L2:
        diff = q - v
        sq = float(np.dot(diff, diff))
        if sq < 0.0:
            sq = 0.0
        return float(np.sqrt(sq))
    if metric_space is MetricSpace.COSINE:
        return float(1.0 - np.dot(q, v))
    # DOT — higher similarity better → negate.
    return float(-np.dot(q, v))


def score_query_recall(
    gt_ids: Sequence[int],
    returned_ids: Sequence[int],
    *,
    returned_true_distances: Sequence[float | None],
    d_k: float,
    n_eff: int,
    rtol: float = CANARY_RTOL,
) -> tuple[float, float, QueryRecallDiag]:
    """Per-query recall_id and tie-tolerant recall_dist (§2.2, ADR-0007).

    ``returned_true_distances`` entries are ``None`` when the ID is invalid /
    missing from the corpus (counts as a miss, not a distance hit).
    """
    if n_eff <= 0:
        msg = "n_eff must be > 0"
        raise ValueError(msg)

    gt_set = {int(x) for x in gt_ids if int(x) >= 0}
    short_return = len(returned_ids) < n_eff or any(int(x) < 0 for x in returned_ids)

    seen: dict[int, bool] = {}
    unique_returned: list[int] = []
    duplicate_returns = 0
    for rid in returned_ids:
        ir = int(rid)
        if ir < 0:
            continue
        if ir in seen:
            duplicate_returns += 1
            continue
        seen[ir] = True
        unique_returned.append(ir)

    hits_id = sum(1 for rid in unique_returned if rid in gt_set)
    recall_id = hits_id / float(n_eff)

    threshold = float(d_k) * (1.0 + float(rtol))
    hits_dist = 0
    seen_dist: dict[int, bool] = {}
    returned_invalid = 0
    for rid, dist in zip(returned_ids, returned_true_distances, strict=True):
        ir = int(rid)
        if ir < 0:
            continue
        if ir in seen_dist:
            continue
        seen_dist[ir] = True
        if dist is None:
            returned_invalid += 1
            continue
        if float(dist) <= threshold:
            hits_dist += 1
    recall_dist = hits_dist / float(n_eff)

    boundary_tie = recall_dist > recall_id + 1e-15
    return (
        recall_id,
        recall_dist,
        QueryRecallDiag(
            short_return=short_return,
            duplicate_returns=duplicate_returns,
            returned_invalid=returned_invalid,
            boundary_tie=boundary_tie,
            snapshot_inconsistent=0,
        ),
    )


def bootstrap_ci95(
    values: Sequence[float],
    *,
    n_resamples: int = _DEFAULT_BOOTSTRAP,
    seed: int,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap 95% CI over per-query scores (§2.3 step 5)."""
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"))
    arr = np.asarray(values, dtype=np.float64)
    rng: Generator = default_rng(seed)
    means = np.empty(n_resamples, dtype=np.float64)
    for i in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        means[i] = float(np.mean(arr[idx]))
    lo = float(np.quantile(means, alpha / 2.0))
    hi = float(np.quantile(means, 1.0 - alpha / 2.0))
    return (lo, hi)


def _materialise_corpus(
    *,
    corpus_ids: NDArray[np.int64] | None,
    corpus_vectors: NDArray[np.floating] | None,
    corpus_batches: Iterable[VectorBatch] | None,
) -> tuple[NDArray[np.int64], NDArray[np.float32], dict[int, int]]:
    if corpus_batches is not None:
        batches = list(corpus_batches)
        if not batches:
            empty_ids = np.asarray([], dtype=np.int64)
            empty_vecs = np.zeros((0, 0), dtype=np.float32)
            return empty_ids, empty_vecs, {}
        ids = np.concatenate([b.ids for b in batches])
        vecs = np.concatenate([b.vectors for b in batches], axis=0)
    elif corpus_ids is not None and corpus_vectors is not None:
        ids = np.asarray(corpus_ids, dtype=np.int64)
        vecs = np.ascontiguousarray(corpus_vectors, dtype=np.float32)
    else:
        msg = "provide corpus_ids+corpus_vectors or corpus_batches"
        raise ValueError(msg)
    id_to_row: dict[int, int] = {}
    for i in range(int(ids.shape[0])):
        id_to_row[int(ids[i])] = i
    return ids, vecs, id_to_row


def _evidence_for(
    *,
    query_source: str,
    n_queries: int,
    truncated: bool,
) -> EvidenceStrength:
    if truncated or n_queries < _LOW_EVIDENCE_Q:
        return EvidenceStrength.LOW
    if query_source == "file":
        return EvidenceStrength.HIGH
    return EvidenceStrength.MEDIUM


def _unavailable(
    reason: str,
    *,
    sampling: Mapping[str, Any],
    detail: Mapping[str, Any],
    evidence: EvidenceStrength,
    warn: float,
    fail: float,
) -> MetricResult:
    return MetricResult(
        id=CANARY_METRIC_ID,
        state=MetricState.UNAVAILABLE,
        value=None,
        unit="ratio",
        thresholds=ThresholdSpec(warn=warn, fail=fail, direction="lower_is_worse"),
        sampling=dict(sampling),
        detail=dict(detail),
        evidence_strength=evidence,
        unavailable_reason=reason,
    )


def compute_canary_recall(
    *,
    queries: NDArray[np.floating],
    returned_ids: NDArray[np.int64],
    metric_space: MetricSpace,
    k: int,
    search_params: Mapping[str, Any],
    corpus_ids: NDArray[np.int64] | None = None,
    corpus_vectors: NDArray[np.floating] | None = None,
    corpus_batches: Iterable[VectorBatch] | None = None,
    query_source_ids: NDArray[np.int64] | None = None,
    self_exclude: bool = True,
    query_source: str = "corpus",
    working_set_mb: float = 256.0,
    bootstrap_resamples: int = _DEFAULT_BOOTSTRAP,
    bootstrap_seed: int = 1337,
    live_ids_at_start: frozenset[int] | None = None,
    ground_truth_truncated: bool = False,
    engine_distances: NDArray[np.floating] | None = None,
    warn: float = CANARY_WARN,
    fail: float = CANARY_FAIL,
    rtol: float = CANARY_RTOL,
    enforce_min_queries: bool = True,
    eligible_ids: frozenset[int] | None = None,
) -> MetricResult:
    """Compute canary recall against blocked exact ground truth (§2).

    Parameters
    ----------
    engine_distances:
        Ignored when provided — present only so callers cannot accidentally
        wire engine scores into the metric (ADR-0007).
    enforce_min_queries:
        When True (default), ``Q < 5`` → ``UNAVAILABLE`` (§2.4). Oracle
        fixtures may disable this to assert a single hand-verified query.
    """
    del engine_distances  # never trusted (ADR-0007)

    q = np.ascontiguousarray(queries, dtype=np.float32)
    ret = np.asarray(returned_ids, dtype=np.int64)
    n_queries = int(q.shape[0])

    sampling: dict[str, Any] = {
        "queries": n_queries,
        "k": k,
        "query_source": query_source,
        "self_excluded": bool(self_exclude and query_source_ids is not None),
        "search_params": dict(search_params),
    }
    base_detail: dict[str, Any] = {
        "recall_id": None,
        "recall_dist": None,
        "ci95": None,
        "returned_invalid": 0,
        "short_returns": 0,
        "duplicate_returns": 0,
        "boundary_ties": 0,
        "truncated": bool(ground_truth_truncated),
        "snapshot_inconsistent": False,
    }

    if enforce_min_queries and n_queries < _MIN_QUERIES:
        return _unavailable(
            f"Q={n_queries} < {_MIN_QUERIES} (insufficient queries)",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )

    ids, vecs, id_to_row = _materialise_corpus(
        corpus_ids=corpus_ids,
        corpus_vectors=corpus_vectors,
        corpus_batches=corpus_batches,
    )
    if eligible_ids is not None:
        keep_idx = [i for i in range(int(ids.shape[0])) if int(ids[i]) in eligible_ids]
        if keep_idx:
            idx = np.asarray(keep_idx, dtype=np.int64)
            ids = ids[idx]
            vecs = vecs[idx]
            id_to_row = {int(ids[i]): i for i in range(int(ids.shape[0]))}
        else:
            ids = np.asarray([], dtype=np.int64)
            vecs = np.zeros((0, 0), dtype=np.float32)
            id_to_row = {}
    n_live = int(ids.shape[0])
    if n_live == 0:
        return _unavailable(
            "n_live == 0 (empty live corpus)",
            sampling=sampling,
            detail=base_detail,
            evidence=_evidence_for(
                query_source=query_source,
                n_queries=n_queries,
                truncated=ground_truth_truncated,
            ),
            warn=warn,
            fail=fail,
        )

    # Request k+1 when self-excluding so we can drop the query id and keep k.
    need_extra = bool(self_exclude and query_source_ids is not None)
    gt_k = k + 1 if need_extra else k
    batches = [VectorBatch(ids=ids, vectors=vecs)]
    gt = exact_knn(
        batches,
        q,
        gt_k,
        metric_space,
        working_set_mb=working_set_mb,
        n_total=n_live,
    )
    truncated = bool(ground_truth_truncated or gt.truncated)

    per_id: list[float] = []
    per_dist: list[float] = []
    short_returns = 0
    duplicate_returns = 0
    returned_invalid = 0
    boundary_ties = 0
    snapshot_inconsistent = False
    start_set = live_ids_at_start

    for qi in range(n_queries):
        exclude_id: int | None = None
        if need_extra and query_source_ids is not None:
            exclude_id = int(query_source_ids[qi])

        row_ids: list[int] = []
        row_dists: list[float] = []
        for j in range(gt_k):
            gid = int(gt.ids[qi, j])
            if gid < 0:
                continue
            if exclude_id is not None and gid == exclude_id:
                continue
            row_ids.append(gid)
            row_dists.append(float(gt.distances[qi, j]))
            if len(row_ids) >= k:
                break

        eligible = n_live
        if exclude_id is not None and exclude_id in id_to_row:
            eligible = n_live - 1
        n_eff = min(k, max(0, eligible))
        if n_eff == 0:
            return _unavailable(
                "n_eff == 0 (no eligible live neighbours for a query)",
                sampling=sampling,
                detail=base_detail,
                evidence=_evidence_for(
                    query_source=query_source,
                    n_queries=n_queries,
                    truncated=truncated,
                ),
                warn=warn,
                fail=fail,
            )

        d_k = row_dists[n_eff - 1] if len(row_dists) >= n_eff else float("inf")
        gt_take = row_ids[:n_eff]

        # Returned row (pad-aware). Drop the query's own id when self-excluding
        # so a trivial distance-0 hit cannot inflate recall_dist (ADR-0007).
        ret_row = (
            [int(x) for x in ret[qi].tolist()]
            if ret.ndim == 2
            else [int(x) for x in ret.tolist()]
        )
        while len(ret_row) < k:
            ret_row.append(-1)
        if exclude_id is not None:
            ret_row = [rid if rid != exclude_id else -1 for rid in ret_row]

        true_dists: list[float | None] = []
        snap_hits = 0
        for rid in ret_row[: max(k, len(ret_row))]:
            if rid < 0:
                true_dists.append(None)
                continue
            row = id_to_row.get(rid)
            if row is None:
                true_dists.append(None)
                if start_set is not None and rid in start_set:
                    snap_hits += 1
                    snapshot_inconsistent = True
                continue
            true_dists.append(_pairwise_true_distance(q[qi], vecs[row], metric_space))

        # Align lengths for zip.
        use_ids = ret_row[: len(true_dists)]
        rid_s, rdist_s, diag = score_query_recall(
            gt_take,
            use_ids,
            returned_true_distances=true_dists,
            d_k=d_k,
            n_eff=n_eff,
            rtol=rtol,
        )
        # Invalid tally: unknown/dead among non-padding returns.
        inv = 0
        seen_inv: dict[int, bool] = {}
        for rid, dist in zip(use_ids, true_dists, strict=True):
            if rid < 0:
                continue
            if rid in seen_inv:
                continue
            seen_inv[rid] = True
            if dist is None:
                inv += 1
        diag_invalid = inv
        if snap_hits:
            snapshot_inconsistent = True

        per_id.append(rid_s)
        per_dist.append(rdist_s)
        if diag.short_return or sum(1 for x in use_ids if x >= 0) < n_eff:
            short_returns += 1
        duplicate_returns += diag.duplicate_returns
        returned_invalid += diag_invalid
        if diag.boundary_tie:
            boundary_ties += 1

    mean_id = float(np.mean(np.asarray(per_id, dtype=np.float64)))
    mean_dist = float(np.mean(np.asarray(per_dist, dtype=np.float64)))
    ci_lo, ci_hi = bootstrap_ci95(
        per_dist,
        n_resamples=bootstrap_resamples,
        seed=bootstrap_seed,
    )
    # Ensure CI contains the point estimate (percentile bootstrap can miss
    # on tiny Q; expand to include the mean).
    ci_lo = min(ci_lo, mean_dist)
    ci_hi = max(ci_hi, mean_dist)

    evidence = _evidence_for(
        query_source=query_source,
        n_queries=n_queries,
        truncated=truncated,
    )
    state = state_from_recall_dist(mean_dist, warn=warn, fail=fail)
    # §1.4: low-evidence metrics may never produce FAIL alone.
    if evidence is EvidenceStrength.LOW and state is MetricState.FAIL:
        state = MetricState.WARN

    detail: dict[str, Any] = {
        "recall_id": mean_id,
        "recall_dist": mean_dist,
        "ci95": [ci_lo, ci_hi],
        "returned_invalid": returned_invalid,
        "short_returns": short_returns,
        "duplicate_returns": duplicate_returns,
        "boundary_ties": boundary_ties,
        "truncated": truncated,
        "snapshot_inconsistent": snapshot_inconsistent,
    }
    return MetricResult(
        id=CANARY_METRIC_ID,
        state=state,
        value=mean_dist,
        unit="ratio",
        thresholds=ThresholdSpec(warn=warn, fail=fail, direction="lower_is_worse"),
        sampling=sampling,
        detail=detail,
        evidence_strength=evidence,
        explanation=(
            "Tie-tolerant canary recall (recall_dist gates; recall_id reported)."
        ),
    )
