"""P2-04: blocked BLAS exact_knn vs naive oracle + invariance."""

from __future__ import annotations

import math
from collections.abc import Iterator

import numpy as np
import pytest
from numpy.random import default_rng
from vhecfsck.core.ground_truth import (
    KnnResult,
    block_rows_for_working_set,
    exact_knn,
    float64_crosscheck_ids,
)
from vhecfsck.models import MetricSpace, VectorBatch

from tests.oracle.reference import naive_knn


def _batches(
    vectors: np.ndarray,
    ids: np.ndarray | None = None,
    *,
    chunk: int = 32,
) -> Iterator[VectorBatch]:
    n = int(vectors.shape[0])
    if ids is None:
        ids = np.arange(n, dtype=np.int64)
    # Upcast storage formats at the boundary the way adapters will.
    if vectors.dtype == np.float16:
        base = vectors.astype(np.float32)
    else:
        base = np.ascontiguousarray(vectors, dtype=np.float32)
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        yield VectorBatch(
            ids=ids[start:stop].copy(),
            vectors=np.ascontiguousarray(base[start:stop]),
        )


def _rel_close(a: float, b: float, rtol: float = 1e-5, atol: float = 1e-6) -> bool:
    # Spec §2.6: 1e-5 relative. Near-zero scores need a tiny absolute floor so
    # float32 sgemm vs float64-of-float32 naive loops are comparable.
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def _assert_knn_agree(
    got: KnnResult,
    naive_ids: np.ndarray,
    naive_dist: np.ndarray,
    *,
    require_id_match: bool,
) -> None:
    q, k = naive_ids.shape
    assert got.ids.shape == (q, k)
    assert got.distances.shape == (q, k)
    assert got.d_k.shape == (q,)
    assert got.truncated is False
    for qi in range(q):
        for j in range(k):
            if require_id_match:
                assert int(got.ids[qi, j]) == int(naive_ids[qi, j])
            assert _rel_close(float(got.distances[qi, j]), float(naive_dist[qi, j]))
        # d_K is the distance to the last filled neighbour slot.
        last = k - 1
        while last >= 0 and int(got.ids[qi, last]) < 0:
            last -= 1
        if last >= 0:
            assert _rel_close(float(got.d_k[qi]), float(got.distances[qi, last]))


@pytest.mark.parametrize("space", list(MetricSpace))
def test_differential_vs_naive_randomised(space: MetricSpace) -> None:
    """200 randomised cases: IDs match on tie-free inputs; distances within 1e-5 rel."""
    rng = default_rng(20260829)
    cases = 0
    # Keep inputs tiny so the deliberate naive oracle stays cheap (lesson U).
    for _ in range(40):
        n = int(rng.integers(8, 48))
        d = int(rng.integers(2, 12))
        q_n = int(rng.integers(1, 6))
        k = int(rng.integers(1, min(8, n) + 1))
        corpus = rng.standard_normal((n, d)).astype(np.float64)
        queries = rng.standard_normal((q_n, d)).astype(np.float64)
        if space is MetricSpace.COSINE:
            for row in range(n):
                norm = math.sqrt(sum(float(x) * float(x) for x in corpus[row]))
                corpus[row] = corpus[row] / norm
            for row in range(q_n):
                norm = math.sqrt(sum(float(x) * float(x) for x in queries[row]))
                queries[row] = queries[row] / norm
        # Compare against the float32 values the blocked path actually sees.
        corpus_f32 = corpus.astype(np.float32)
        queries_f32 = queries.astype(np.float32)
        n_ids, n_dist = naive_knn(
            corpus_f32.astype(np.float64),
            queries_f32.astype(np.float64),
            k,
            space,
        )
        for block_hint in (1, 7, max(1, n // 3), n):
            working = _working_set_mb_for_rows(block_hint, d=d, n_queries=q_n)
            got = exact_knn(
                _batches(corpus_f32, chunk=max(1, block_hint)),
                queries_f32,
                k,
                space,
                working_set_mb=working,
                n_total=n,
            )
            _assert_knn_agree(got, n_ids, n_dist, require_id_match=True)
            cases += 1
    assert cases >= 160


def _working_set_mb_for_rows(block_rows: int, *, d: int, n_queries: int) -> float:
    """Invert block_rows_for_working_set so tests pin exact B values."""
    # B = max(1, floor(budget_bytes / (4 * (D + Q))))
    # Choose budget so floor division yields exactly block_rows.
    unit = 4 * (d + n_queries)
    budget_bytes = block_rows * unit + (unit - 1)  # still floors to block_rows
    return budget_bytes / (1024.0 * 1024.0)


def test_block_size_invariance() -> None:
    """Identical results at B ∈ {1, 7, 999, n} — the highest-value test in P2-04."""
    rng = default_rng(7)
    n, d, q_n, k = 1200, 16, 5, 10
    corpus = rng.standard_normal((n, d)).astype(np.float32)
    queries = rng.standard_normal((q_n, d)).astype(np.float32)
    results: list[KnnResult] = []
    for b in (1, 7, 999, n):
        working = _working_set_mb_for_rows(b, d=d, n_queries=q_n)
        # Feed awkward chunk sizes so re-blocking is exercised.
        got = exact_knn(
            _batches(corpus, chunk=13),
            queries,
            k,
            MetricSpace.L2,
            working_set_mb=working,
            n_total=n,
        )
        assert got.truncated is False
        results.append(got)
    ref = results[0]
    for other in results[1:]:
        assert other.ids.tobytes() == ref.ids.tobytes()
        for qi in range(q_n):
            for j in range(k):
                assert _rel_close(
                    float(other.distances[qi, j]),
                    float(ref.distances[qi, j]),
                )


def test_duplicate_vectors_tie_break_ascending_id() -> None:
    corpus = np.asarray(
        [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        dtype=np.float32,
    )
    queries = np.asarray([[1.0, 0.0]], dtype=np.float32)
    got = exact_knn(
        _batches(corpus, chunk=1),
        queries,
        k=2,
        metric_space=MetricSpace.L2,
        working_set_mb=_working_set_mb_for_rows(1, d=2, n_queries=1),
        n_total=3,
    )
    assert int(got.ids[0, 0]) == 0
    assert int(got.ids[0, 1]) == 1


def test_k_greater_than_n_pads_and_sets_d_k() -> None:
    corpus = np.asarray([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    queries = np.asarray([[0.0, 0.0]], dtype=np.float32)
    got = exact_knn(
        _batches(corpus),
        queries,
        k=5,
        metric_space=MetricSpace.L2,
        working_set_mb=1.0,
        n_total=2,
    )
    assert got.ids.shape == (1, 5)
    assert int(got.ids[0, 0]) == 0
    assert int(got.ids[0, 1]) == 1
    assert int(got.ids[0, 2]) == -1
    assert float(got.d_k[0]) == pytest.approx(float(got.distances[0, 1]))


def test_l2_near_identical_never_nan() -> None:
    """Clamp before sqrt — ADR-0005 silent-nan bug."""
    # Near-identical float32 vectors force cancellation in ||a||^2+||b||^2-2a.b.
    base = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    corpus = np.stack([base, base * np.float32(1.0 + 1e-7)], axis=0)
    queries = base.reshape(1, -1).copy()
    got = exact_knn(
        _batches(corpus, chunk=1),
        queries,
        k=2,
        metric_space=MetricSpace.L2,
        working_set_mb=_working_set_mb_for_rows(1, d=4, n_queries=1),
        n_total=2,
    )
    for j in range(2):
        d = float(got.distances[0, j])
        assert d == d  # not NaN
        assert d >= 0.0


def test_float16_input_upcast_on_read() -> None:
    rng = default_rng(3)
    corpus64 = rng.standard_normal((20, 8))
    queries64 = rng.standard_normal((3, 8))
    corpus16 = corpus64.astype(np.float16)
    # Oracle sees the same float32 values the blocked path accumulates.
    corpus32 = corpus16.astype(np.float32)
    queries32 = queries64.astype(np.float32)
    k = 4
    naive_ids, naive_dist = naive_knn(
        corpus32.astype(np.float64),
        queries32.astype(np.float64),
        k,
        MetricSpace.L2,
    )
    got = exact_knn(
        _batches(corpus16, chunk=5),
        queries32,
        k,
        MetricSpace.L2,
        working_set_mb=_working_set_mb_for_rows(5, d=8, n_queries=3),
        n_total=20,
    )
    _assert_knn_agree(got, naive_ids, naive_dist, require_id_match=True)


def test_float64_crosscheck_helper() -> None:
    rng = default_rng(11)
    corpus = rng.standard_normal((30, 6)).astype(np.float32)
    queries = rng.standard_normal((4, 6)).astype(np.float32)
    assert float64_crosscheck_ids(
        corpus,
        queries,
        k=5,
        metric_space=MetricSpace.L2,
        working_set_mb=_working_set_mb_for_rows(7, d=6, n_queries=4),
    )


def test_progress_and_deadline_truncated() -> None:
    rng = default_rng(5)
    n, d = 400, 8
    corpus = rng.standard_normal((n, d)).astype(np.float32)
    queries = rng.standard_normal((2, d)).astype(np.float32)
    seen: list[float] = []

    def on_progress(frac: float) -> None:
        seen.append(float(frac))

    full = exact_knn(
        _batches(corpus, chunk=20),
        queries,
        k=3,
        metric_space=MetricSpace.DOT,
        working_set_mb=_working_set_mb_for_rows(20, d=d, n_queries=2),
        n_total=n,
        on_progress=on_progress,
    )
    assert full.truncated is False
    assert seen
    assert seen[-1] == pytest.approx(1.0)

    truncated = exact_knn(
        _batches(corpus, chunk=20),
        queries,
        k=3,
        metric_space=MetricSpace.DOT,
        working_set_mb=_working_set_mb_for_rows(20, d=d, n_queries=2),
        n_total=n,
        max_seconds=0.0,
    )
    assert truncated.truncated is True


def test_block_rows_derived_from_working_set_not_constant() -> None:
    b_small = block_rows_for_working_set(working_set_mb=1.0, dim=768, n_queries=200)
    b_large = block_rows_for_working_set(working_set_mb=256.0, dim=768, n_queries=200)
    assert b_small >= 1
    assert b_large > b_small
    # Peak score matrix Q*B*4 plus block B*D*4 stays under the budget.
    budget = 256.0 * 1024.0 * 1024.0
    peak = b_large * 768 * 4 + 200 * b_large * 4
    assert peak <= budget


def test_single_vs_multi_thread_blas_ids_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance: same IDs with OMP=1 and OMP=2 on tie-free data (ADR-0005)."""
    rng = default_rng(99)
    corpus = rng.standard_normal((80, 32)).astype(np.float32)
    queries = rng.standard_normal((4, 32)).astype(np.float32)
    working = _working_set_mb_for_rows(16, d=32, n_queries=4)

    def run_with_threads(n_threads: str) -> KnnResult:
        monkeypatch.setenv("OMP_NUM_THREADS", n_threads)
        monkeypatch.setenv("OPENBLAS_NUM_THREADS", n_threads)
        monkeypatch.setenv("MKL_NUM_THREADS", n_threads)
        return exact_knn(
            _batches(corpus, chunk=16),
            queries,
            k=5,
            metric_space=MetricSpace.L2,
            working_set_mb=working,
            n_total=80,
        )

    a = run_with_threads("1")
    b = run_with_threads("2")
    assert a.ids.tobytes() == b.ids.tobytes()


def test_input_validation_errors() -> None:
    with pytest.raises(ValueError, match="working_set_mb"):
        block_rows_for_working_set(0.0, dim=8, n_queries=2)
    with pytest.raises(ValueError, match="dim and n_queries"):
        block_rows_for_working_set(1.0, dim=0, n_queries=2)
    corpus = np.asarray([[0.0, 1.0]], dtype=np.float32)
    queries = np.asarray([[0.0, 1.0]], dtype=np.float32)
    with pytest.raises(ValueError, match="k must be"):
        exact_knn(_batches(corpus), queries, k=0, metric_space=MetricSpace.L2)
    with pytest.raises(ValueError, match="rank-2"):
        exact_knn(
            _batches(corpus),
            np.asarray([0.0, 1.0], dtype=np.float32),
            k=1,
            metric_space=MetricSpace.L2,
        )


def test_float64_crosscheck_cosine_and_dot() -> None:
    rng = default_rng(17)
    corpus = rng.standard_normal((24, 5)).astype(np.float32)
    # Unit-normalise for cosine.
    for i in range(corpus.shape[0]):
        nrm = float(np.sqrt(np.sum(corpus[i] * corpus[i])))
        corpus[i] = corpus[i] / np.float32(nrm)
    queries = corpus[:3].copy()
    working = _working_set_mb_for_rows(8, d=5, n_queries=3)
    assert float64_crosscheck_ids(
        corpus, queries, k=4, metric_space=MetricSpace.COSINE, working_set_mb=working
    )
    assert float64_crosscheck_ids(
        corpus, queries, k=4, metric_space=MetricSpace.DOT, working_set_mb=working
    )


def test_empty_corpus_yields_padded_result() -> None:
    queries = np.asarray([[1.0, 0.0]], dtype=np.float32)
    got = exact_knn([], queries, k=3, metric_space=MetricSpace.L2, n_total=0)
    assert got.truncated is False
    assert int(got.ids[0, 0]) == -1
    assert float(got.d_k[0]) == float("inf")


def test_duplicate_id_across_blocks_deduped() -> None:
    """Same id appearing in two blocks keeps the better distance once."""
    from vhecfsck.core import ground_truth as gt

    best_ids = np.asarray([5, -1, -1], dtype=np.int64)
    best_dist = np.asarray([0.5, np.inf, np.inf], dtype=np.float32)
    cand_ids = np.asarray([5, 7], dtype=np.int64)
    cand_dist = np.asarray([0.4, 0.9], dtype=np.float32)
    gt._merge_query_topk(best_ids, best_dist, cand_ids, cand_dist, k=3)
    assert int(best_ids[0]) == 5
    assert float(best_dist[0]) == pytest.approx(0.4)
    assert int(best_ids[1]) == 7
