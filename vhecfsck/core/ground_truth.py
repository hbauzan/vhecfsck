"""Blocked BLAS exact k-NN ground truth (P2-04).

Implements ``02-metrics-spec.md`` §2.3 and ADR-0005: stream corpus blocks sized
from ``working_set_mb``, one ``sgemm`` per block, merge top-``k`` with
ascending-ID tie-break, ``float32`` accumulation (``float16`` upcast on read),
L2 clamp-before-sqrt.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from vhecfsck.models import MetricSpace, VectorBatch


@dataclass(frozen=True)
class KnnResult:
    """Exact k-NN output for a query batch.

    ``ids`` / ``distances`` are shape ``(n_queries, k)`` with ``-1`` / ``+inf``
    padding when fewer than ``k`` corpus rows exist. ``d_k[q]`` is the distance
    to the last filled neighbour of query ``q`` (``+inf`` if none).
    """

    ids: NDArray[np.int64]
    distances: NDArray[np.float32]
    d_k: NDArray[np.float32]
    truncated: bool


def block_rows_for_working_set(
    working_set_mb: float,
    *,
    dim: int,
    n_queries: int,
) -> int:
    """Derive block row count from the working-set budget (never a constant).

    Budget covers one corpus block ``B*D*4`` plus the score panel ``Q*B*4``
    (``02-metrics-spec.md`` §2.3).
    """
    if working_set_mb <= 0:
        msg = "working_set_mb must be > 0"
        raise ValueError(msg)
    if dim < 1 or n_queries < 1:
        msg = "dim and n_queries must be >= 1"
        raise ValueError(msg)
    budget_bytes = float(working_set_mb) * 1024.0 * 1024.0
    unit = 4 * (dim + n_queries)
    rows = int(budget_bytes // unit)
    return max(1, rows)


def _as_float32_block(vectors: NDArray[np.floating]) -> NDArray[np.float32]:
    """Upcast storage dtypes (incl. float16) to float32 for accumulation."""
    return np.ascontiguousarray(vectors, dtype=np.float32)


def _score_block(
    queries: NDArray[np.float32],
    block: NDArray[np.float32],
    metric_space: MetricSpace,
    query_norm2: NDArray[np.float32] | None,
) -> NDArray[np.float32]:
    """Lower-is-better scores, shape ``(Q, B)``, via one BLAS matmul."""
    # Contiguous float32 @ float32.T -> sgemm.
    dots_arr = queries @ block.T
    dots: NDArray[np.float32] = np.asarray(dots_arr, dtype=np.float32)
    if metric_space is MetricSpace.DOT:
        out: NDArray[np.float32] = np.asarray(-dots, dtype=np.float32)
        return out
    if metric_space is MetricSpace.COSINE:
        # Callers supply unit vectors; distance = 1 - cos.
        cos_out: NDArray[np.float32] = np.asarray(
            np.float32(1.0) - dots, dtype=np.float32
        )
        return cos_out
    # L2: ||q||^2 + ||x||^2 - 2 q.x, clamp tiny negatives, then sqrt.
    if query_norm2 is None:
        msg = "query_norm2 required for L2"
        raise RuntimeError(msg)
    qn: NDArray[np.float32] = query_norm2
    block_norm2: NDArray[np.float32] = np.asarray(
        np.sum(block * block, axis=1, dtype=np.float32),
        dtype=np.float32,
    )
    sq: NDArray[np.float32] = np.asarray(
        qn[:, None] + block_norm2[None, :] - (np.float32(2.0) * dots),
        dtype=np.float32,
    )
    # Cancellation near duplicates yields ~-1e-7; unclamped -> nan (ADR-0005).
    np.maximum(sq, np.float32(0.0), out=sq)
    dist: NDArray[np.float32] = np.asarray(np.sqrt(sq), dtype=np.float32)
    return dist


_PAD_ID = np.iinfo(np.int64).max


def _merge_queries_topk(
    best_ids: NDArray[np.int64],
    best_dist: NDArray[np.float32],
    cand_ids: NDArray[np.int64],
    cand_dist: NDArray[np.float32],
    k: int,
) -> None:
    """In-place merge of running top-k with block candidates, all queries.

    Bit-exact with the per-query Python loop: sort by ``(distance, id)``,
    skip duplicate ids, pad with ``-1`` / ``+inf``. Does not rescore — the
    GEMM identity ``|q|^2+|c|^2-2qc`` is forbidden here (lesson 61).
    """
    n_q = int(best_ids.shape[0])
    if n_q == 0 or k < 1:
        return
    ids = np.concatenate(
        [np.asarray(best_ids, dtype=np.int64), np.asarray(cand_ids, dtype=np.int64)],
        axis=1,
    )
    dist = np.concatenate(
        [
            np.asarray(best_dist, dtype=np.float32),
            np.asarray(cand_dist, dtype=np.float32),
        ],
        axis=1,
    )
    n_slots = int(ids.shape[1])
    valid = ids >= 0
    work_ids = np.where(valid, ids, _PAD_ID)
    work_dist = np.where(valid, dist, np.float32(np.inf))
    rec = np.empty(ids.shape, dtype=[("d", np.float32), ("i", np.int64)])
    rec["d"] = work_dist
    rec["i"] = work_ids
    rec.sort(axis=1, order=("d", "i"))
    sorted_ids = rec["i"]
    sorted_dist = rec["d"]
    out_ids = np.full((n_q, k), -1, dtype=np.int64)
    out_dist = np.full((n_q, k), np.float32(np.inf), dtype=np.float32)
    filled = np.zeros(n_q, dtype=np.intp)
    for col in range(n_slots):
        vid = sorted_ids[:, col]
        vdist = sorted_dist[:, col]
        take_mask = (filled < k) & (vid != _PAD_ID)
        if not np.any(take_mask):
            continue
        already = (out_ids == vid[:, None]).any(axis=1)
        take_mask &= ~already
        rows = np.flatnonzero(take_mask)
        if rows.size == 0:
            continue
        dest = filled[rows]
        out_ids[rows, dest] = vid[rows]
        out_dist[rows, dest] = vdist[rows]
        filled[rows] += 1
        if int(filled.min()) >= k:
            break
    best_ids[:, :] = out_ids
    best_dist[:, :] = out_dist


def _merge_query_topk(
    best_ids: NDArray[np.int64],
    best_dist: NDArray[np.float32],
    cand_ids: NDArray[np.int64],
    cand_dist: NDArray[np.float32],
    k: int,
) -> None:
    """In-place merge of one query's running top-k with a block's candidates."""
    _merge_queries_topk(
        np.asarray(best_ids).reshape(1, -1),
        np.asarray(best_dist).reshape(1, -1),
        np.asarray(cand_ids).reshape(1, -1),
        np.asarray(cand_dist).reshape(1, -1),
        k,
    )


def _block_topk(
    scores: NDArray[np.float32],
    id_row: NDArray[np.int64],
    k: int,
) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
    """Top-k within one block for every query; ties by ascending id.

    Bit-exact with per-row ``argpartition`` + Python sort. Does not rescore.
    """
    n_q = int(scores.shape[0])
    n_block = int(scores.shape[1]) if scores.ndim == 2 else 0
    take = min(k, n_block)
    if take == 0:
        return (
            np.full((n_q, 0), -1, dtype=np.int64),
            np.full((n_q, 0), np.float32(np.inf), dtype=np.float32),
        )
    rec = np.empty((n_q, take), dtype=[("d", np.float32), ("i", np.int64)])
    if take == n_block:
        rec["d"] = scores
        rec["i"] = id_row[None, :]
    else:
        part = np.argpartition(scores, take - 1, axis=1)[:, :take]
        rec["d"] = np.take_along_axis(scores, part, axis=1)
        rec["i"] = id_row[part]
    rec.sort(axis=1, order=("d", "i"))
    out_ids: NDArray[np.int64] = np.asarray(rec["i"], dtype=np.int64)
    out_dist: NDArray[np.float32] = np.asarray(rec["d"], dtype=np.float32)
    return out_ids, out_dist


def _block_topk_indices(
    scores_row: NDArray[np.float32],
    id_row: NDArray[np.int64],
    k: int,
) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
    """Top-k within one block for a single query; ties by ascending id."""
    ids, dist = _block_topk(np.asarray(scores_row).reshape(1, -1), id_row, k)
    return ids[0], dist[0]


def _iter_reblocked(
    corpus_iter: Iterable[VectorBatch],
    block_rows: int,
) -> Iterator[tuple[NDArray[np.int64], NDArray[np.float32]]]:
    """Re-chunk arbitrary VectorBatch sizes into blocks of at most ``block_rows``."""
    buf_ids: list[NDArray[np.int64]] = []
    buf_vecs: list[NDArray[np.float32]] = []
    buffered = 0

    def flush(n_take: int) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
        nonlocal buffered
        ids_cat = np.concatenate(buf_ids, axis=0)
        vecs_cat = np.concatenate(buf_vecs, axis=0)
        out_ids = ids_cat[:n_take].copy()
        out_vecs = np.ascontiguousarray(vecs_cat[:n_take])
        rest_ids = ids_cat[n_take:]
        rest_vecs = vecs_cat[n_take:]
        buf_ids.clear()
        buf_vecs.clear()
        buffered = int(rest_ids.shape[0])
        if buffered:
            buf_ids.append(rest_ids)
            buf_vecs.append(rest_vecs)
        return out_ids, out_vecs

    for batch in corpus_iter:
        vecs = _as_float32_block(batch.vectors)
        buf_ids.append(np.asarray(batch.ids, dtype=np.int64))
        buf_vecs.append(vecs)
        buffered += int(vecs.shape[0])
        while buffered >= block_rows:
            yield flush(block_rows)
    if buffered > 0:
        yield flush(buffered)


def exact_knn(
    corpus_iter: Iterable[VectorBatch],
    queries: NDArray[np.floating],
    k: int,
    metric_space: MetricSpace,
    *,
    working_set_mb: float = 256.0,
    on_progress: Callable[[float], None] | None = None,
    max_seconds: float | None = None,
    n_total: int | None = None,
) -> KnnResult:
    """Exact k-NN by blocked BLAS (``02-metrics-spec.md`` §2.3, ADR-0005).

    Parameters
    ----------
    corpus_iter:
        Stream of ``VectorBatch`` values (any batch size). Re-blocked internally
        from ``working_set_mb``.
    queries:
        Query matrix ``(Q, D)``. Upcast to ``float32``; cosine queries must
        already be L2-normalised.
    k:
        Neighbours per query. When ``k`` exceeds the corpus size, unused slots
        stay at ``-1`` / ``+inf`` (edge case 1 / padding).
    metric_space:
        ``L2`` | ``COSINE`` | ``DOT``.
    working_set_mb:
        Peak working set for one block + score panel; drives ``B``.
    on_progress:
        Optional ``fraction`` in ``[0, 1]`` when ``n_total`` is known.
    max_seconds:
        Soft deadline. On expiry, returns with ``truncated=True`` and whatever
        top-k has been merged so far (never presented as complete).
    n_total:
        Optional corpus cardinality for progress reporting.
    """
    if k < 1:
        msg = "k must be >= 1"
        raise ValueError(msg)
    q = np.ascontiguousarray(queries, dtype=np.float32)
    if q.ndim != 2:
        msg = "queries must be rank-2 (Q, D)"
        raise ValueError(msg)
    n_queries, dim = int(q.shape[0]), int(q.shape[1])
    block_rows = block_rows_for_working_set(
        working_set_mb, dim=dim, n_queries=n_queries
    )

    best_ids = np.full((n_queries, k), -1, dtype=np.int64)
    best_dist = np.full((n_queries, k), np.float32(np.inf), dtype=np.float32)
    query_norm2: NDArray[np.float32] | None = None
    if metric_space is MetricSpace.L2:
        query_norm2 = np.sum(q * q, axis=1, dtype=np.float32)

    started = time.monotonic()
    rows_done = 0
    truncated = False

    for ids_block, vecs_block in _iter_reblocked(corpus_iter, block_rows):
        if max_seconds is not None and (time.monotonic() - started) >= max_seconds:
            truncated = True
            break
        scores = _score_block(q, vecs_block, metric_space, query_norm2)
        cand_ids, cand_dist = _block_topk(scores, ids_block, k)
        _merge_queries_topk(best_ids, best_dist, cand_ids, cand_dist, k)
        rows_done += int(ids_block.shape[0])
        if on_progress is not None and n_total is not None and n_total > 0:
            on_progress(min(1.0, float(rows_done) / float(n_total)))
        if max_seconds is not None and (time.monotonic() - started) >= max_seconds:
            truncated = True
            break

    if (
        on_progress is not None
        and n_total is not None
        and n_total > 0
        and not truncated
    ):
        on_progress(1.0)

    d_k = np.full(n_queries, np.float32(np.inf), dtype=np.float32)
    for qi in range(n_queries):
        last = k - 1
        while last >= 0 and int(best_ids[qi, last]) < 0:
            last -= 1
        if last >= 0:
            d_k[qi] = best_dist[qi, last]

    return KnnResult(ids=best_ids, distances=best_dist, d_k=d_k, truncated=truncated)


def float64_crosscheck_ids(
    corpus: NDArray[np.floating],
    queries: NDArray[np.floating],
    k: int,
    metric_space: MetricSpace,
    *,
    working_set_mb: float,
) -> bool:
    """True when float32 blocked path matches float64 neighbour ID ordering.

    Used by tests on a small slice (ADR-0005). Disagreement means the float32
    tolerance assumption needs revisiting — do not loosen silently.
    """
    n = int(corpus.shape[0])
    ids = np.arange(n, dtype=np.int64)

    def as_batches(
        matrix: NDArray[np.floating],
    ) -> list[VectorBatch]:
        vecs = np.ascontiguousarray(matrix, dtype=np.float32)
        return [VectorBatch(ids=ids, vectors=vecs)]

    # float32 path (production dtype).
    f32 = exact_knn(
        as_batches(corpus),
        queries,
        k,
        metric_space,
        working_set_mb=working_set_mb,
        n_total=n,
    )
    # float64 reference path: score in float64, same merge rules.
    q64 = np.ascontiguousarray(queries, dtype=np.float64)
    c64 = np.ascontiguousarray(corpus, dtype=np.float64)
    if metric_space is MetricSpace.L2:
        qn = np.sum(q64 * q64, axis=1)
        cn = np.sum(c64 * c64, axis=1)
        dots = q64 @ c64.T
        sq = qn[:, None] + cn[None, :] - 2.0 * dots
        sq = np.maximum(sq, 0.0)
        scores = np.sqrt(sq)
    elif metric_space is MetricSpace.COSINE:
        scores = 1.0 - (q64 @ c64.T)
    else:
        scores = -(q64 @ c64.T)

    n_queries = int(q64.shape[0])
    take = min(k, n)
    ref_ids = np.full((n_queries, k), -1, dtype=np.int64)
    for qi in range(n_queries):
        order = list(range(n))
        order.sort(key=lambda i: (float(scores[qi, i]), int(ids[i])))
        for j in range(take):
            ref_ids[qi, j] = ids[order[j]]
    return f32.ids.tobytes() == ref_ids.tobytes()
