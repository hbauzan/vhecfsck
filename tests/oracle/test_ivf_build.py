"""Differential test pinning the vectorised IVF build to the loop reference.

The vectorised ``_fit_ivf`` is not "close enough" to the loop it replaced — it is
byte-identical, which is what lets the golden report fixtures stay untouched.
That claim only holds for one specific spelling of the arithmetic, so it is
asserted here on raw bytes rather than on a tolerance.

Two shapes that break exactness and must never be reintroduced:

* the GEMM identity ``|q|^2 + |c|^2 - 2qc`` instead of ``sqrt(sum(diff*diff))``
  (max error 1.95e-3 on the 8k fixture);
* ``vectors[assignment == c].sum(axis=0)`` instead of ``np.add.at``, because
  pairwise summation does not reproduce the sequential accumulation order.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.random import default_rng
from vhecfsck.adapters.synthetic_adapter import (
    _KMEANS_ITERS,
    _distance_panel,
    _fit_ivf,
    _pairwise_distances,
    _panel_chunk_rows,
)
from vhecfsck.models import MetricSpace

from tests.oracle.reference_ivf import (
    KMEANS_ITERS,
    naive_fit_ivf,
    naive_pairwise_distances,
)

METRICS = (MetricSpace.L2, MetricSpace.COSINE, MetricSpace.DOT)


def _corpus(n: int, d: int, *, seed: int, metric: MetricSpace) -> np.ndarray:
    """Seeded float32 corpus; unit-normalised for COSINE as the generator does."""
    rng = default_rng(seed)
    vectors = np.asarray(rng.normal(size=(n, d)), dtype=np.float32)
    if metric is MetricSpace.COSINE:
        norms = np.sqrt(np.sum(vectors * vectors, axis=1, dtype=np.float32))
        norms[norms == np.float32(0.0)] = np.float32(1.0)
        vectors = vectors / norms[:, None]
    return np.ascontiguousarray(vectors, dtype=np.float32)


def _assert_build_is_byte_identical(
    vectors: np.ndarray,
    *,
    n_lists: int,
    seed: int,
    metric: MetricSpace,
) -> None:
    got_c, got_a, got_lists = _fit_ivf(
        vectors,
        n_lists=n_lists,
        seed=seed,
        metric=metric,
    )
    ref_c, ref_a, ref_lists = naive_fit_ivf(
        vectors,
        n_lists=n_lists,
        seed=seed,
        metric=metric,
    )

    assert got_c.dtype == ref_c.dtype
    assert got_c.shape == ref_c.shape
    assert got_c.tobytes() == ref_c.tobytes()

    assert got_a.dtype == ref_a.dtype
    assert got_a.shape == ref_a.shape
    assert got_a.tobytes() == ref_a.tobytes()

    assert len(got_lists) == len(ref_lists)
    for cell, (got_cell, ref_cell) in enumerate(zip(got_lists, ref_lists, strict=True)):
        assert got_cell.dtype == ref_cell.dtype, cell
        assert got_cell.tobytes() == ref_cell.tobytes(), cell


def test_iteration_count_matches_the_reference() -> None:
    """A change to the production sweep count must not silently skip the oracle."""
    assert _KMEANS_ITERS == KMEANS_ITERS


@pytest.mark.parametrize("metric", METRICS)
@pytest.mark.parametrize(
    ("n", "d", "n_lists"),
    [(2000, 16, 16), (500, 64, 24), (80, 8, 4)],
)
def test_build_matches_loop_reference(
    metric: MetricSpace,
    n: int,
    d: int,
    n_lists: int,
) -> None:
    """Centroids, assignment and every list are byte-identical to the loop."""
    vectors = _corpus(n, d, seed=7, metric=metric)
    _assert_build_is_byte_identical(vectors, n_lists=n_lists, seed=3, metric=metric)


@pytest.mark.slow
@pytest.mark.parametrize("metric", METRICS)
def test_build_matches_loop_reference_at_fixture_scale(metric: MetricSpace) -> None:
    """The (8000, 16, 32) shape of the healthy/small scenario, the costly one."""
    vectors = _corpus(8000, 16, seed=11, metric=metric)
    _assert_build_is_byte_identical(vectors, n_lists=32, seed=0, metric=metric)


@pytest.mark.parametrize("metric", METRICS)
def test_build_matches_loop_reference_when_n_below_n_lists(
    metric: MetricSpace,
) -> None:
    """Padded-centroid branch: fewer rows than lists still matches the loop."""
    vectors = _corpus(5, 3, seed=5, metric=metric)
    _assert_build_is_byte_identical(vectors, n_lists=8, seed=1, metric=metric)


@pytest.mark.parametrize("metric", METRICS)
def test_padded_lists_stay_empty_when_n_below_n_lists(metric: MetricSpace) -> None:
    """Ascending tie-break: duplicated pad centroids never win a row."""
    n, n_lists = 5, 8
    vectors = _corpus(n, 3, seed=5, metric=metric)
    _, assignment, lists = _fit_ivf(vectors, n_lists=n_lists, seed=1, metric=metric)

    assert int(assignment.max()) < n
    assert sum(int(cell.shape[0]) for cell in lists) == n
    for cell in lists[n:]:
        assert int(cell.shape[0]) == 0


@pytest.mark.parametrize("metric", METRICS)
def test_empty_corpus_matches_loop_reference(metric: MetricSpace) -> None:
    """Zero rows short-circuits to empty centroids and one empty list per cell."""
    vectors = np.empty((0, 4), dtype=np.float32)
    _assert_build_is_byte_identical(vectors, n_lists=3, seed=0, metric=metric)


@pytest.mark.parametrize("metric", METRICS)
def test_distance_panel_matches_scalar_distance(metric: MetricSpace) -> None:
    """The panel equals the per-row scalar path still used by IVF search."""
    vectors = _corpus(37, 12, seed=2, metric=metric)
    centroids = _corpus(9, 12, seed=4, metric=metric)
    panel = _distance_panel(vectors, centroids, metric, chunk=8)

    assert panel.dtype == np.float32
    assert panel.shape == (37, 9)
    for i in range(int(vectors.shape[0])):
        expected = naive_pairwise_distances(centroids, vectors[i], metric)
        assert panel[i].tobytes() == expected.tobytes(), i
        production = _pairwise_distances(centroids, vectors[i], metric)
        assert panel[i].tobytes() == production.tobytes(), i


@pytest.mark.parametrize("metric", METRICS)
@pytest.mark.parametrize("chunk", [1, 7, 999, 4096])
def test_distance_panel_is_chunk_size_invariant(
    metric: MetricSpace,
    chunk: int,
) -> None:
    """Row chunking only trades memory for calls; it never moves a bit."""
    vectors = _corpus(101, 6, seed=13, metric=metric)
    centroids = _corpus(5, 6, seed=17, metric=metric)
    whole = _distance_panel(vectors, centroids, metric, chunk=int(vectors.shape[0]))
    chunked = _distance_panel(vectors, centroids, metric, chunk=chunk)
    assert chunked.tobytes() == whole.tobytes()


def test_panel_chunk_rows_respects_the_memory_budget() -> None:
    """Chunk width shrinks as the panel row grows, and never reaches zero."""
    wide = _panel_chunk_rows(1024, 1536)
    narrow = _panel_chunk_rows(4, 8)
    assert wide >= 1
    assert narrow > wide
    assert wide * 1024 * 1536 * 4 <= 64 * 1024 * 1024
