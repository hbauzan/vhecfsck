"""P2-02: Deterministic sampling module tests."""

from __future__ import annotations

import numpy as np
from vhecfsck.core.sampling import (
    bootstrap_indices,
    derive_rng,
    sample_without_replacement,
)


def test_derive_rng_reproducible_and_independent_per_purpose() -> None:
    root_seed = 42
    rng_canary1 = derive_rng(root_seed, "canary_queries")
    rng_canary2 = derive_rng(root_seed, "canary_queries")
    rng_hubness = derive_rng(root_seed, "hubness_sample")

    draw_canary1 = rng_canary1.integers(0, 1000, size=10)
    draw_canary2 = rng_canary2.integers(0, 1000, size=10)
    draw_hubness = rng_hubness.integers(0, 1000, size=10)

    np.testing.assert_array_equal(draw_canary1, draw_canary2)
    assert not np.array_equal(draw_canary1, draw_hubness)


def test_derive_rng_new_purpose_does_not_shift_existing() -> None:
    root_seed = 123
    draw1 = derive_rng(root_seed, "purpose_a").random(5)
    # Introducing purpose_b does not alter purpose_a draw
    _ = derive_rng(root_seed, "purpose_b").random(5)
    draw1_again = derive_rng(root_seed, "purpose_a").random(5)

    np.testing.assert_array_equal(draw1, draw1_again)


def test_sample_without_replacement_sorted_and_reproducible() -> None:
    ids = np.array([10, 5, 20, 1, 8, 15, 3, 9], dtype=np.int64)
    rng = derive_rng(99, "test_sample")
    sampled = sample_without_replacement(ids, 4, rng)

    assert len(sampled) == 4
    # Result must be sorted for deterministic downstream ordering
    np.testing.assert_array_equal(sampled, np.sort(sampled))
    assert all(item in ids for item in sampled)


def test_sample_without_replacement_exceeding_or_equal_size() -> None:
    ids = np.array([30, 10, 20], dtype=np.int64)
    rng = derive_rng(1, "test_exceed")
    sampled = sample_without_replacement(ids, 10, rng)

    np.testing.assert_array_equal(sampled, np.array([10, 20, 30], dtype=np.int64))


def test_bootstrap_indices_shape_and_range() -> None:
    rng = derive_rng(777, "bootstrap")
    res = bootstrap_indices(n=50, resamples=100, rng=rng)

    assert res.shape == (100, 50)
    assert np.all((res >= 0) & (res < 50))
