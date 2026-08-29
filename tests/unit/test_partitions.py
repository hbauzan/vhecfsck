"""P2-08: partition size CV unit tests (Fixture C + §5.3 edges)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from vhecfsck.core.partitions import (
    PARTITION_CV_FAIL,
    PARTITION_CV_METRIC_ID,
    PARTITION_CV_WARN,
    compute_partition_cv,
    population_cv,
    state_from_partition_cv,
)
from vhecfsck.models import (
    EvidenceStrength,
    GraphStats,
    MetricSpace,
    MetricState,
    PartitionStats,
)
from vhecfsck.models.metrics import Direction
from vhecfsck.synthetic import (
    corpus_state_from_generated,
    generate_corpus,
    skew_partitions,
)


def _stats(sizes: list[int], *, includes_deleted: bool = False) -> PartitionStats:
    arr = np.asarray(sizes, dtype=np.int64)
    return PartitionStats(
        sizes=arr,
        includes_deleted=includes_deleted,
        n_partitions=int(arr.shape[0]),
    )


def test_fixture_c_exact() -> None:
    """Fixture C — §5.4: must never be deleted or modernised."""
    sizes = [500, 500, 500, 80000]
    mean = sum(sizes) / float(len(sizes))
    var = sum((s - mean) ** 2 for s in sizes) / float(len(sizes))  # ddof=0
    expected_cv = math.sqrt(var) / mean
    # ddof=1 would differ — lock the population value.
    sample_var = sum((s - mean) ** 2 for s in sizes) / float(len(sizes) - 1)
    sample_cv = math.sqrt(sample_var) / mean
    assert expected_cv != pytest.approx(sample_cv)

    result = compute_partition_cv(_stats(sizes))
    assert result.value == pytest.approx(1.6895464932727084)
    assert result.value == pytest.approx(expected_cv)
    assert result.detail["max_over_mean"] == pytest.approx(3.9263803680981595)
    assert result.state is MetricState.WARN  # > 1.20, < 2.00
    assert result.id == PARTITION_CV_METRIC_ID
    assert result.thresholds.direction is Direction.HIGHER_IS_WORSE


def test_population_cv_ddof_zero_explicit() -> None:
    sizes = [500, 500, 500, 80000]
    assert population_cv(sizes) == pytest.approx(1.6895464932727084)


def test_edge_not_applicable() -> None:
    """§5.3 case 1: non-IVF → UNAVAILABLE(not_applicable)."""
    result = compute_partition_cv(_stats([10, 10, 10]), applicable=False)
    assert result.state is MetricState.UNAVAILABLE
    assert result.unavailable_reason == "not_applicable"


def test_edge_n_partitions_le_one() -> None:
    """§5.3 case 2."""
    result = compute_partition_cv(_stats([100]))
    assert result.state is MetricState.UNAVAILABLE
    assert "n_partitions" in (result.unavailable_reason or "")


def test_edge_n_partitions_lt_eight_low_evidence() -> None:
    """§5.3 case 3."""
    result = compute_partition_cv(_stats([10, 10, 10, 10]))
    assert result.state is not MetricState.UNAVAILABLE
    assert result.evidence_strength is EvidenceStrength.LOW


def test_edge_all_empty_unavailable() -> None:
    """§5.3 case 4."""
    result = compute_partition_cv(_stats([0, 0, 0, 0]))
    assert result.state is MetricState.UNAVAILABLE
    assert result.unavailable_reason == "empty_index"
    assert result.detail["empty_index"] is True


def test_edge_includes_deleted_flag() -> None:
    """§5.3 case 5: physical counts flagged."""
    result = compute_partition_cv(_stats([5, 5, 5, 5], includes_deleted=True))
    assert result.detail["includes_deleted"] is True
    assert result.sampling["includes_deleted"] is True


def test_edge_index_name_keyed() -> None:
    """§5.3 case 6: one instance keyed by index name."""
    result = compute_partition_cv(_stats([5, 5, 5, 5]), index_name="idx_vecs")
    assert result.sampling["index_name"] == "idx_vecs"


def test_graph_stats_path_unavailable() -> None:
    """HNSW in-degree variant accepted but UNAVAILABLE until adapters supply it."""
    gs = GraphStats(
        in_degree_histogram=np.asarray([1, 2, 3], dtype=np.int64),
        entry_point_ids=np.asarray([0], dtype=np.int64),
        entrypoint_tombstoned=False,
    )
    result = compute_partition_cv(None, graph_stats=gs)
    assert result.state is MetricState.UNAVAILABLE


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.20, MetricState.OK),
        (1.200001, MetricState.WARN),
        (2.00, MetricState.WARN),
        (2.000001, MetricState.FAIL),
    ],
)
def test_threshold_boundaries(value: float, expected: MetricState) -> None:
    assert (
        state_from_partition_cv(value, warn=PARTITION_CV_WARN, fail=PARTITION_CV_FAIL)
        is expected
    )


def test_skew_partitions_target_cv_within_5_percent() -> None:
    gen = generate_corpus(
        800,
        8,
        n_clusters=8,
        cluster_std=0.15,
        cluster_size_skew=0.5,
        seed=5,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    out = skew_partitions(state, target_cv=1.5, seed=2)
    assert out.annotation.partition_cv is not None
    sizes = list(out.annotation.partition_sizes or ())
    result = compute_partition_cv(_stats(list(sizes)))
    assert result.value == pytest.approx(1.5, rel=0.05)
