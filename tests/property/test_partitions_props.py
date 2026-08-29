"""Property tests for partition size CV (P2-08)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.core.partitions import compute_partition_cv, population_cv
from vhecfsck.models import PartitionStats


def _stats(sizes: list[int]) -> PartitionStats:
    arr = np.asarray(sizes, dtype=np.int64)
    return PartitionStats(
        sizes=arr,
        includes_deleted=False,
        n_partitions=int(arr.shape[0]),
    )


def test_cv_non_negative() -> None:
    result = compute_partition_cv(_stats([1, 2, 3, 4, 5, 6, 7, 8]))
    assert result.value is not None
    assert float(result.value) >= 0.0


def test_uniform_sizes_cv_zero() -> None:
    result = compute_partition_cv(_stats([10, 10, 10, 10, 10, 10, 10, 10]))
    assert result.value == 0.0


def test_permutation_invariant() -> None:
    a = compute_partition_cv(_stats([1, 5, 2, 8, 3, 7, 4, 6]))
    b = compute_partition_cv(_stats([8, 6, 4, 2, 7, 5, 3, 1]))
    assert a.value == b.value
    assert a.detail["max_over_mean"] == b.detail["max_over_mean"]


def test_scale_invariant() -> None:
    a = compute_partition_cv(_stats([1, 2, 3, 4, 5, 6, 7, 8]))
    b = compute_partition_cv(_stats([10, 20, 30, 40, 50, 60, 70, 80]))
    assert a.value == pytest.approx(b.value)


def test_monotonic_under_mass_concentration() -> None:
    base = [10] * 8
    mild = list(base)
    mild[0] = 20
    heavy = list(base)
    heavy[0] = 80
    r0 = population_cv(base)
    r1 = population_cv(mild)
    r2 = population_cv(heavy)
    assert r0 <= r1 <= r2
