"""Hubness metrics — ``02-metrics-spec.md`` §3 (P2-06).

Independent self-queried subsample ``S`` (ADR-0006 / CORRECTION 3). Never
materialises ``S x S``; reuses blocked ``exact_knn`` from ``ground_truth``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any, Literal

import numpy as np
from numpy.random import Generator, default_rng
from numpy.typing import NDArray

from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.errors import InternalError
from vhecfsck.models import (
    EvidenceStrength,
    MetricResult,
    MetricSpace,
    MetricState,
    ThresholdSpec,
    VectorBatch,
)
from vhecfsck.models.metrics import Direction

HubnessSource = Literal["truth", "engine"]

HUB_SHARE_METRIC_ID = "hub_share_top1pct"
ANTIHUB_METRIC_ID = "antihub_fraction"
HUB_SHARE_WARN = 0.20
HUB_SHARE_FAIL = 0.35
ANTIHUB_WARN = 0.25
ANTIHUB_FAIL = 0.40
CALIBRATION_S = 20_000
CALIBRATION_K_HUB = 10
_MIN_SAMPLE = 1000
_MAX_OFFENDER_IDS = 1000
_DEFAULT_MAD_MULTIPLIER = 5.0


def state_from_hub_share(
    value: float,
    *,
    warn: float = HUB_SHARE_WARN,
    fail: float = HUB_SHARE_FAIL,
) -> MetricState:
    """Map hub share to OK/WARN/FAIL (``higher_is_worse``, §3)."""
    if value > fail:
        return MetricState.FAIL
    if value > warn:
        return MetricState.WARN
    return MetricState.OK


def state_from_antihub(
    value: float,
    *,
    warn: float = ANTIHUB_WARN,
    fail: float = ANTIHUB_FAIL,
) -> MetricState:
    """Map anti-hub fraction to OK/WARN/FAIL (``higher_is_worse``, §3)."""
    if value > fail:
        return MetricState.FAIL
    if value > warn:
        return MetricState.WARN
    return MetricState.OK


def hub_share_top1pct_from_nk(n_k: NDArray[np.int64]) -> float:
    """``sum(top ceil(0.01·|S|) N_k) / sum(N_k)`` (§3.1)."""
    s = int(n_k.shape[0])
    if s == 0:
        return 0.0
    total = int(np.sum(n_k))
    if total == 0:
        return 0.0
    top_n = math.ceil(0.01 * s)
    values = sorted((int(n_k[i]) for i in range(s)), reverse=True)
    top_sum = sum(values[:top_n])
    return top_sum / float(total)


def antihub_fraction_from_nk(n_k: NDArray[np.int64]) -> float:
    """``|{x : N_k(x) == 0}| / |S|`` (§3.1)."""
    s = int(n_k.shape[0])
    if s == 0:
        return 0.0
    zeros = sum(1 for i in range(s) if int(n_k[i]) == 0)
    return zeros / float(s)


def count_nk_from_neighbour_ids(
    neighbour_ids: NDArray[np.int64],
    *,
    sample_ids: NDArray[np.int64],
    k_hub: int,
    assert_invariant: bool = True,
) -> NDArray[np.int64]:
    """Count ``N_k`` appearances from per-query neighbour id lists.

    ``neighbour_ids`` shape ``(S, k_hub)`` with ``-1`` padding. Raises
    :class:`InternalError` when ``sum(N_k) != S · k_hub`` and
    ``assert_invariant`` is True (§3.6 case 7).
    """
    s = int(sample_ids.shape[0])
    id_to_idx: dict[int, int] = {int(sample_ids[i]): i for i in range(s)}
    counts = np.zeros(s, dtype=np.int64)
    n_q = int(neighbour_ids.shape[0])
    k_cols = int(neighbour_ids.shape[1]) if neighbour_ids.ndim == 2 else 0
    for qi in range(n_q):
        for j in range(k_cols):
            nid = int(neighbour_ids[qi, j])
            if nid < 0:
                continue
            idx = id_to_idx.get(nid)
            if idx is not None:
                counts[idx] += 1
    if assert_invariant:
        total = int(np.sum(counts))
        expected = s * k_hub
        if total != expected:
            msg = (
                f"sum(N_k)={total} != S*k_hub={expected} "
                "(internal hubness invariant violated)"
            )
            raise InternalError(msg)
    return counts


def _self_exclude_neighbours(
    gt_ids: NDArray[np.int64],
    sample_ids: NDArray[np.int64],
    k_hub: int,
) -> NDArray[np.int64]:
    """Drop each query's own id from blocked k-NN output (§3.1)."""
    s = int(sample_ids.shape[0])
    out = np.full((s, k_hub), -1, dtype=np.int64)
    for qi in range(s):
        exclude = int(sample_ids[qi])
        taken = 0
        for j in range(int(gt_ids.shape[1])):
            gid = int(gt_ids[qi, j])
            if gid < 0:
                break
            if gid == exclude:
                continue
            out[qi, taken] = gid
            taken += 1
            if taken >= k_hub:
                break
    return out


def _sample_live_ids(
    live_ids: NDArray[np.int64],
    n: int,
    rng: Generator,
) -> NDArray[np.int64]:
    """Deterministic subsample without replacement; sorted output."""
    n_live = int(live_ids.shape[0])
    take = min(n, n_live)
    if take >= n_live:
        return np.sort(live_ids)
    idx = rng.choice(n_live, size=take, replace=False)
    return np.sort(live_ids[idx])


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


def _fetch_sample(
    vecs: NDArray[np.float32],
    id_to_row: Mapping[int, int],
    sample_ids: NDArray[np.int64],
) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
    rows: list[int] = []
    for sid in sample_ids:
        row = id_to_row.get(int(sid))
        if row is None:
            msg = f"sample id {int(sid)} not found in corpus"
            raise ValueError(msg)
        rows.append(row)
    row_idx = np.asarray(rows, dtype=np.int64)
    return (
        np.asarray(sample_ids, dtype=np.int64),
        np.ascontiguousarray(vecs[row_idx], dtype=np.float32),
    )


def _duplicate_vector_pairs(vectors: NDArray[np.float32]) -> int:
    """Exact float32 duplicates within the sample (§3.5)."""
    s = int(vectors.shape[0])
    if s < 2:
        return 0
    seen: dict[bytes, int] = {}
    pairs = 0
    for i in range(s):
        key = vectors[i].tobytes()
        prev = seen.get(key)
        if prev is not None:
            pairs += 1
        else:
            seen[key] = i
    return pairs


def _norm_p99_ratio(vectors: NDArray[np.float32]) -> float:
    norms = np.sqrt(np.sum(vectors * vectors, axis=1, dtype=np.float32))
    if norms.size == 0:
        return 1.0
    p99 = float(np.quantile(norms, 0.99))
    med = float(np.median(norms))
    if med <= 0.0:
        return 1.0
    return p99 / med


def _histogram_bucketed(
    n_k: NDArray[np.int64],
    *,
    max_buckets: int = 64,
) -> list[dict[str, int]]:
    mx = int(np.max(n_k)) if n_k.size else 0
    if mx <= max_buckets:
        return [
            {"lo": v, "hi": v, "count": int(np.sum(n_k == v))} for v in range(mx + 1)
        ]
    width = math.ceil((mx + 1) / float(max_buckets))
    buckets: list[dict[str, int]] = []
    for b in range(max_buckets):
        lo = b * width
        hi = min(mx, lo + width - 1)
        if lo > mx:
            break
        mask = (n_k >= lo) & (n_k <= hi)
        count = int(np.sum(mask))
        if count > 0 or b == 0:
            buckets.append({"lo": lo, "hi": hi, "count": count})
    return buckets


def _mad_outlier_count(
    n_k: NDArray[np.int64],
    *,
    multiplier: float,
) -> int:
    if n_k.size == 0:
        return 0
    med = float(np.median(n_k))
    dev = np.abs(n_k.astype(np.float64) - med)
    mad = float(np.median(dev))
    if mad == 0.0:
        return 0
    threshold = med + multiplier * mad
    return int(np.sum(n_k.astype(np.float64) > threshold))


def _offender_ids(
    n_k: NDArray[np.int64],
    sample_ids: NDArray[np.int64],
    *,
    top: bool,
    cap: int = _MAX_OFFENDER_IDS,
) -> list[int]:
    s = int(n_k.shape[0])
    indexed = [(int(n_k[i]), int(sample_ids[i]), i) for i in range(s)]
    if top:
        indexed.sort(key=lambda t: (-t[0], t[1]))
        return [t[1] for t in indexed[:cap] if t[0] > 0]
    # Anti-hubs: N_k == 0 first, then lowest N_k.
    indexed.sort(key=lambda t: (t[0], t[1]))
    out: list[int] = []
    for nk, sid, _ in indexed:
        if nk > 0 and not out:
            break
        if nk == 0:
            out.append(sid)
        if len(out) >= cap:
            break
    return out


def _build_diagnostics(
    n_k: NDArray[np.int64],
    sample_ids: NDArray[np.int64],
    vectors: NDArray[np.float32],
    *,
    mad_multiplier: float,
    uncalibrated: bool,
) -> dict[str, Any]:
    return {
        "n_k": [int(x) for x in n_k.tolist()],
        "max_nk": int(np.max(n_k)) if n_k.size else 0,
        "p99_nk": float(np.quantile(n_k, 0.99)) if n_k.size else 0.0,
        "median_nk": float(np.median(n_k)) if n_k.size else 0.0,
        "histogram": _histogram_bucketed(n_k),
        "hub_outlier_count": _mad_outlier_count(n_k, multiplier=mad_multiplier),
        "hub_ids": _offender_ids(n_k, sample_ids, top=True),
        "antihub_ids": _offender_ids(n_k, sample_ids, top=False),
        "duplicate_vector_pairs": _duplicate_vector_pairs(vectors),
        "norm_p99_ratio": _norm_p99_ratio(vectors),
        "thresholds_uncalibrated_for_sample_size": uncalibrated,
        "mad_multiplier": mad_multiplier,
    }


def _unavailable_pair(
    reason: str,
    *,
    sampling: Mapping[str, Any],
    detail: Mapping[str, Any],
    evidence: EvidenceStrength,
    share_warn: float,
    share_fail: float,
    anti_warn: float,
    anti_fail: float,
) -> tuple[MetricResult, MetricResult]:
    share = MetricResult(
        id=HUB_SHARE_METRIC_ID,
        state=MetricState.UNAVAILABLE,
        value=None,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=share_warn, fail=share_fail, direction=Direction.HIGHER_IS_WORSE
        ),
        sampling=dict(sampling),
        detail=dict(detail),
        evidence_strength=evidence,
        unavailable_reason=reason,
    )
    anti = MetricResult(
        id=ANTIHUB_METRIC_ID,
        state=MetricState.UNAVAILABLE,
        value=None,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=anti_warn, fail=anti_fail, direction=Direction.HIGHER_IS_WORSE
        ),
        sampling=dict(sampling),
        detail=dict(detail),
        evidence_strength=evidence,
        unavailable_reason=reason,
    )
    return share, anti


def compute_hubness(
    *,
    metric_space: MetricSpace,
    k_hub: int = CALIBRATION_K_HUB,
    hubness_source: HubnessSource = "truth",
    sample_size: int = CALIBRATION_S,
    sample_seed: int = 1337,
    corpus_ids: NDArray[np.int64] | None = None,
    corpus_vectors: NDArray[np.floating] | None = None,
    corpus_batches: Iterable[VectorBatch] | None = None,
    sample_ids: NDArray[np.int64] | None = None,
    engine_neighbour_ids: NDArray[np.int64] | None = None,
    working_set_mb: float = 256.0,
    enforce_min_sample: bool = True,
    mad_multiplier: float = _DEFAULT_MAD_MULTIPLIER,
    share_warn: float = HUB_SHARE_WARN,
    share_fail: float = HUB_SHARE_FAIL,
    anti_warn: float = ANTIHUB_WARN,
    anti_fail: float = ANTIHUB_FAIL,
) -> tuple[MetricResult, MetricResult]:
    """Compute hub share and anti-hub fraction (§3, ADR-0006).

    Parameters
    ----------
    hubness_source:
      ``truth`` (blocked exact k-NN) or ``engine`` (caller-supplied neighbour
      ids of shape ``(S, k_hub)``).
    enforce_min_sample:
      When True (default), ``|S| < 1000`` → ``UNAVAILABLE``. Oracle fixtures
      may disable this for hand-verified micro-samples (Fixture B).
    """
    ids, vecs, id_to_row = _materialise_corpus(
        corpus_ids=corpus_ids,
        corpus_vectors=corpus_vectors,
        corpus_batches=corpus_batches,
    )
    n_live = int(ids.shape[0])

    sampling: dict[str, Any] = {
        "S": 0,
        "k_hub": k_hub,
        "hubness_source": hubness_source,
        "sample_seed": sample_seed,
        "requested_sample_size": sample_size,
        "decoupled_from_canary": True,
    }
    base_detail: dict[str, Any] = {
        "hub_share_top1pct": None,
        "antihub_fraction": None,
    }

    if n_live == 0:
        return _unavailable_pair(
            "n_live == 0 (empty live corpus)",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            share_warn=share_warn,
            share_fail=share_fail,
            anti_warn=anti_warn,
            anti_fail=anti_fail,
        )

    if sample_ids is None:
        rng: Generator = default_rng(sample_seed)
        chosen = _sample_live_ids(ids, sample_size, rng)
    else:
        chosen = np.asarray(sample_ids, dtype=np.int64)

    s_count = int(chosen.shape[0])
    sampling["S"] = s_count

    if enforce_min_sample and s_count < _MIN_SAMPLE:
        return _unavailable_pair(
            f"|S|={s_count} < {_MIN_SAMPLE} (hubness sample too small)",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            share_warn=share_warn,
            share_fail=share_fail,
            anti_warn=anti_warn,
            anti_fail=anti_fail,
        )

    if k_hub >= s_count:
        return _unavailable_pair(
            f"k_hub={k_hub} >= |S|={s_count}",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            share_warn=share_warn,
            share_fail=share_fail,
            anti_warn=anti_warn,
            anti_fail=anti_fail,
        )

    sample_ids_out, sample_vecs = _fetch_sample(vecs, id_to_row, chosen)

    if hubness_source == "engine":
        if engine_neighbour_ids is None:
            return _unavailable_pair(
                "hubness_source=engine requires engine_neighbour_ids",
                sampling=sampling,
                detail=base_detail,
                evidence=EvidenceStrength.LOW,
                share_warn=share_warn,
                share_fail=share_fail,
                anti_warn=anti_warn,
                anti_fail=anti_fail,
            )
        neighbours = np.asarray(engine_neighbour_ids, dtype=np.int64)
    else:
        batches = [VectorBatch(ids=sample_ids_out, vectors=sample_vecs)]
        gt = exact_knn(
            batches,
            sample_vecs,
            k_hub + 1,
            metric_space,
            working_set_mb=working_set_mb,
            n_total=s_count,
        )
        neighbours = _self_exclude_neighbours(gt.ids, sample_ids_out, k_hub)

    n_k = count_nk_from_neighbour_ids(
        neighbours,
        sample_ids=sample_ids_out,
        k_hub=k_hub,
        assert_invariant=True,
    )

    hub_val = hub_share_top1pct_from_nk(n_k)
    anti_val = antihub_fraction_from_nk(n_k)
    uncalibrated = s_count != CALIBRATION_S or k_hub != CALIBRATION_K_HUB
    diag = _build_diagnostics(
        n_k,
        sample_ids_out,
        sample_vecs,
        mad_multiplier=mad_multiplier,
        uncalibrated=uncalibrated,
    )
    diag["hub_share_top1pct"] = hub_val
    diag["antihub_fraction"] = anti_val

    evidence = (
        EvidenceStrength.MEDIUM
        if s_count >= CALIBRATION_S // 2
        else EvidenceStrength.LOW
    )

    share_result = MetricResult(
        id=HUB_SHARE_METRIC_ID,
        state=state_from_hub_share(hub_val, warn=share_warn, fail=share_fail),
        value=hub_val,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=share_warn, fail=share_fail, direction=Direction.HIGHER_IS_WORSE
        ),
        sampling=dict(sampling),
        detail=dict(diag),
        evidence_strength=evidence,
        explanation="Share of neighbour-list slots held by the top 1% of points.",
    )
    anti_result = MetricResult(
        id=ANTIHUB_METRIC_ID,
        state=state_from_antihub(anti_val, warn=anti_warn, fail=anti_fail),
        value=anti_val,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=anti_warn, fail=anti_fail, direction=Direction.HIGHER_IS_WORSE
        ),
        sampling=dict(sampling),
        detail=dict(diag),
        evidence_strength=evidence,
        explanation="Fraction of sample points never appearing as anyone's neighbour.",
    )
    return share_result, anti_result
