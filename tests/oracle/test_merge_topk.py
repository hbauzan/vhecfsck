"""Differential test pinning vectorised top-k merge to the loop reference.

TH-06: ``_merge_query_topk`` / ``_block_topk`` at large Q are not "close
enough" to the loop they replace — they are byte-identical. That is what
lets golden report fixtures stay untouched. The claim is asserted on raw
bytes, not a tolerance.

Scoring stays in ``_score_block`` (already BLAS). The merge path must not
recompute distances, including the GEMM identity ``|q|^2+|c|^2-2qc``
(max error 1.95e-3, lesson 61).
"""

from __future__ import annotations

import inspect

import numpy as np
from numpy.random import default_rng
from vhecfsck.core import ground_truth as gt

from tests.oracle.reference_merge import (
    naive_block_topk_indices,
    naive_merge_query_topk,
)


def _assert_merge_byte_identical(
    best_ids: np.ndarray,
    best_dist: np.ndarray,
    cand_ids: np.ndarray,
    cand_dist: np.ndarray,
    k: int,
) -> None:
    got_ids = best_ids.copy()
    got_dist = best_dist.copy()
    ref_ids = best_ids.copy()
    ref_dist = best_dist.copy()
    gt._merge_query_topk(got_ids, got_dist, cand_ids, cand_dist, k)
    naive_merge_query_topk(ref_ids, ref_dist, cand_ids, cand_dist, k)
    assert got_ids.dtype == ref_ids.dtype
    assert got_dist.dtype == ref_dist.dtype
    assert got_ids.tobytes() == ref_ids.tobytes()
    assert got_dist.tobytes() == ref_dist.tobytes()


def _assert_block_byte_identical(
    scores_row: np.ndarray,
    id_row: np.ndarray,
    k: int,
) -> None:
    got_ids, got_dist = gt._block_topk_indices(scores_row, id_row, k)
    ref_ids, ref_dist = naive_block_topk_indices(scores_row, id_row, k)
    assert got_ids.dtype == ref_ids.dtype
    assert got_dist.dtype == ref_dist.dtype
    assert got_ids.tobytes() == ref_ids.tobytes()
    assert got_dist.tobytes() == ref_dist.tobytes()


def test_merge_matches_loop_on_duplicate_id() -> None:
    """Existing oracle case: same id across blocks keeps the better distance."""
    best_ids = np.asarray([5, -1, -1], dtype=np.int64)
    best_dist = np.asarray([0.5, np.inf, np.inf], dtype=np.float32)
    cand_ids = np.asarray([5, 7], dtype=np.int64)
    cand_dist = np.asarray([0.4, 0.9], dtype=np.float32)
    _assert_merge_byte_identical(best_ids, best_dist, cand_ids, cand_dist, k=3)


def test_merge_matches_loop_on_padding_and_ties() -> None:
    """Ascending-id tie-break and ``-1`` / ``+inf`` padding stay bit-exact."""
    best_ids = np.asarray([3, 1, -1], dtype=np.int64)
    best_dist = np.asarray([0.2, 0.2, np.inf], dtype=np.float32)
    cand_ids = np.asarray([2, -1, 8], dtype=np.int64)
    cand_dist = np.asarray([0.2, np.inf, 0.9], dtype=np.float32)
    _assert_merge_byte_identical(best_ids, best_dist, cand_ids, cand_dist, k=3)


def test_merge_matches_loop_when_candidates_empty() -> None:
    best_ids = np.asarray([4, -1], dtype=np.int64)
    best_dist = np.asarray([1.5, np.inf], dtype=np.float32)
    cand_ids = np.asarray([], dtype=np.int64)
    cand_dist = np.asarray([], dtype=np.float32)
    _assert_merge_byte_identical(best_ids, best_dist, cand_ids, cand_dist, k=2)


def test_merge_matches_loop_randomised() -> None:
    rng = default_rng(20260902)
    for _ in range(40):
        k = int(rng.integers(1, 8))
        n_best = int(rng.integers(0, k + 1))
        n_cand = int(rng.integers(0, k + 3))
        best_ids = np.full(k, -1, dtype=np.int64)
        best_dist = np.full(k, np.float32(np.inf), dtype=np.float32)
        if n_best:
            best_ids[:n_best] = rng.integers(0, 20, size=n_best, dtype=np.int64)
            best_dist[:n_best] = rng.random(n_best, dtype=np.float32)
        cand_ids = rng.integers(0, 20, size=n_cand, dtype=np.int64)
        cand_dist = rng.random(n_cand, dtype=np.float32)
        if n_cand and int(rng.integers(0, 4)) == 0:
            cand_ids[0] = -1
        _assert_merge_byte_identical(best_ids, best_dist, cand_ids, cand_dist, k)


def test_block_topk_matches_loop_when_k_equals_block() -> None:
    scores = np.asarray([0.4, 0.1, 0.4], dtype=np.float32)
    ids = np.asarray([9, 2, 3], dtype=np.int64)
    _assert_block_byte_identical(scores, ids, k=3)
    _assert_block_byte_identical(scores, ids, k=10)


def test_block_topk_matches_loop_with_argpartition() -> None:
    scores = np.asarray([0.9, 0.2, 0.2, 0.8, 0.1], dtype=np.float32)
    ids = np.asarray([5, 1, 0, 8, 4], dtype=np.int64)
    _assert_block_byte_identical(scores, ids, k=3)


def test_block_topk_matches_loop_randomised() -> None:
    rng = default_rng(7)
    for _ in range(40):
        b = int(rng.integers(1, 24))
        k = int(rng.integers(1, 12))
        scores = rng.random(b, dtype=np.float32)
        ids = rng.integers(0, 100, size=b, dtype=np.int64)
        _assert_block_byte_identical(scores, ids, k)


def test_batched_merge_matches_looping_reference() -> None:
    """All-query merge is byte-identical to applying the loop per row."""
    rng = default_rng(11)
    n_q, k = 17, 5
    best_ids = np.full((n_q, k), -1, dtype=np.int64)
    best_dist = np.full((n_q, k), np.float32(np.inf), dtype=np.float32)
    filled = rng.integers(0, k + 1, size=n_q)
    for qi in range(n_q):
        n = int(filled[qi])
        if n:
            best_ids[qi, :n] = rng.integers(0, 30, size=n, dtype=np.int64)
            best_dist[qi, :n] = rng.random(n, dtype=np.float32)
    n_cand = 4
    cand_ids = rng.integers(0, 30, size=(n_q, n_cand), dtype=np.int64)
    cand_dist = rng.random((n_q, n_cand), dtype=np.float32)
    cand_ids[3, 1] = -1

    got_ids = best_ids.copy()
    got_dist = best_dist.copy()
    gt._merge_queries_topk(got_ids, got_dist, cand_ids, cand_dist, k)

    ref_ids = best_ids.copy()
    ref_dist = best_dist.copy()
    for qi in range(n_q):
        naive_merge_query_topk(
            ref_ids[qi], ref_dist[qi], cand_ids[qi], cand_dist[qi], k
        )

    assert got_ids.tobytes() == ref_ids.tobytes()
    assert got_dist.tobytes() == ref_dist.tobytes()


def test_batched_block_topk_matches_looping_reference() -> None:
    rng = default_rng(13)
    n_q, b, k = 12, 20, 6
    scores = rng.random((n_q, b), dtype=np.float32)
    id_row = np.arange(b, dtype=np.int64) + 100
    got_ids, got_dist = gt._block_topk(scores, id_row, k)
    take = min(k, b)
    ref_ids = np.empty((n_q, take), dtype=np.int64)
    ref_dist = np.empty((n_q, take), dtype=np.float32)
    for qi in range(n_q):
        ids_i, dist_i = naive_block_topk_indices(scores[qi], id_row, k)
        ref_ids[qi] = ids_i
        ref_dist[qi] = dist_i
    assert got_ids.tobytes() == ref_ids.tobytes()
    assert got_dist.tobytes() == ref_dist.tobytes()


def test_merge_and_block_do_not_rescore() -> None:
    """Merge/block top-k must not recompute distances (GEMM identity is forbidden)."""
    src = (
        inspect.getsource(gt._merge_query_topk)
        + inspect.getsource(gt._merge_queries_topk)
        + inspect.getsource(gt._block_topk)
        + inspect.getsource(gt._block_topk_indices)
    )
    assert "@" not in src
    assert "2.0" not in src
    assert "_score_block" not in src
