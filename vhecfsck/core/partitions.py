"""Partition size CV — ``02-metrics-spec.md`` §5 (P2-08).

Population CV with ``ddof=0`` (normative). HNSW in-degree variant accepted
as input shape but reports ``UNAVAILABLE`` until an adapter supplies data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

from vhecfsck.models import (
    EvidenceStrength,
    GraphStats,
    MetricResult,
    MetricState,
    PartitionStats,
    ThresholdSpec,
)
from vhecfsck.models.metrics import Direction

PARTITION_CV_METRIC_ID = "partition_size_cv"
PARTITION_CV_WARN = 1.20
PARTITION_CV_FAIL = 2.00


def state_from_partition_cv(
    value: float,
    *,
    warn: float = PARTITION_CV_WARN,
    fail: float = PARTITION_CV_FAIL,
) -> MetricState:
    """Map partition CV to OK/WARN/FAIL (``higher_is_worse``, §5)."""
    if value > fail:
        return MetricState.FAIL
    if value > warn:
        return MetricState.WARN
    return MetricState.OK


def population_cv(sizes: Sequence[float] | NDArray[np.floating]) -> float:
    """``population_std(sizes) / mean(sizes)`` with ``ddof=0`` (§5.1).

    Partitions are the entire population, not a sample — ``ddof`` is
    explicitly zero at this call site.
    """
    arr = np.asarray(sizes, dtype=np.float64)
    if arr.size == 0:
        msg = "sizes must be non-empty"
        raise ValueError(msg)
    mean = float(np.mean(arr))  # population mean
    if mean == 0.0:
        return float("nan")
    # ddof=0 — population std (normative; ddof=1 would change Fixture C).
    std = float(np.std(arr, ddof=0))
    return std / mean


def _gini(sizes: NDArray[np.float64]) -> float:
    """Gini coefficient of non-negative sizes (0 = perfect equality)."""
    n = int(sizes.shape[0])
    if n == 0:
        return 0.0
    ordered = np.sort(sizes)
    total = float(np.sum(ordered))
    if total == 0.0:
        return 0.0
    index = np.arange(1, n + 1, dtype=np.float64)
    return float((2.0 * np.sum(index * ordered) - (n + 1) * total) / (n * total))


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
        id=PARTITION_CV_METRIC_ID,
        state=MetricState.UNAVAILABLE,
        value=None,
        unit="coefficient_of_variation",
        thresholds=ThresholdSpec(
            warn=warn, fail=fail, direction=Direction.HIGHER_IS_WORSE
        ),
        sampling=dict(sampling),
        detail=dict(detail),
        evidence_strength=evidence,
        unavailable_reason=reason,
    )


def compute_partition_cv(
    partitions: PartitionStats | None,
    *,
    applicable: bool = True,
    graph_stats: GraphStats | None = None,
    index_name: str = "default",
    warn: float = PARTITION_CV_WARN,
    fail: float = PARTITION_CV_FAIL,
) -> MetricResult:
    """IVF partition-size coefficient of variation (§5).

    Parameters
    ----------
    applicable:
        False for non-IVF indexes → ``UNAVAILABLE(not_applicable)``.
    graph_stats:
        Accepted for the post-MVP HNSW in-degree variant; currently always
        yields ``UNAVAILABLE`` (no adapter supplies it yet).
    """
    sampling: dict[str, Any] = {"index_name": index_name}
    base_detail: dict[str, Any] = {
        "max_over_mean": None,
        "p99_over_mean": None,
        "gini": None,
        "empty_partition_fraction": None,
        "n_partitions": None,
        "top_partitions": [],
        "includes_deleted": None,
        "empty_index": False,
    }

    if graph_stats is not None:
        return _unavailable(
            "HNSW in-degree partition CV not yet available from adapters",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )

    if not applicable:
        return _unavailable(
            "not_applicable",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )

    if partitions is None:
        return _unavailable(
            "PartitionStats unavailable",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )

    sizes = np.asarray(partitions.sizes, dtype=np.float64)
    n_partitions = int(partitions.n_partitions)
    sampling["n_partitions"] = n_partitions
    sampling["includes_deleted"] = bool(partitions.includes_deleted)

    if n_partitions <= 1:
        return _unavailable(
            "n_partitions <= 1 (CV meaningless)",
            sampling=sampling,
            detail={**base_detail, "n_partitions": n_partitions},
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )

    mean = float(np.mean(sizes)) if sizes.size else 0.0
    if mean == 0.0:
        return _unavailable(
            "empty_index",
            sampling=sampling,
            detail={
                **base_detail,
                "n_partitions": n_partitions,
                "empty_index": True,
            },
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )

    cv = population_cv(sizes)
    max_size = float(np.max(sizes))
    max_over_mean = max_size / mean
    p99 = float(np.quantile(sizes, 0.99))
    p99_over_mean = p99 / mean
    empty_frac = float(np.sum(sizes == 0.0) / float(sizes.shape[0]))
    gini = _gini(sizes)

    # Top ten partitions by size (stable tie-break: lower index first).
    order = sorted(
        range(int(sizes.shape[0])),
        key=lambda i: (-float(sizes[i]), i),
    )
    top = [{"partition_id": i, "size": int(sizes[i])} for i in order[:10]]

    evidence = EvidenceStrength.LOW if n_partitions < 8 else EvidenceStrength.MEDIUM
    detail: dict[str, Any] = {
        "max_over_mean": max_over_mean,
        "p99_over_mean": p99_over_mean,
        "gini": gini,
        "empty_partition_fraction": empty_frac,
        "n_partitions": n_partitions,
        "top_partitions": top,
        "includes_deleted": bool(partitions.includes_deleted),
        "empty_index": False,
        "cv": cv,
    }
    state = state_from_partition_cv(cv, warn=warn, fail=fail)
    return MetricResult(
        id=PARTITION_CV_METRIC_ID,
        state=state,
        value=cv,
        unit="coefficient_of_variation",
        thresholds=ThresholdSpec(
            warn=warn, fail=fail, direction=Direction.HIGHER_IS_WORSE
        ),
        sampling=sampling,
        detail=detail,
        evidence_strength=evidence,
        explanation=("IVF partition-size CV (population std / mean, ddof=0)."),
    )
