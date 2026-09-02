"""Loop-based reference for exact k-NN block top-k and top-k merge.

This is the implementation that ``vhecfsck/core/ground_truth.py`` shipped
before TH-06 vectorised the per-query loop: a Python list merge with nested
``seen``-scan, and a per-row ``argpartition`` + Python sort. Transcribed
verbatim so it stays an independent check rather than a rename of the
production path.

Never optimise this module
(``roadmap/archive/lessons-learned-historical.md`` §27). If a test is too
slow, shrink the input. Production code under ``vhecfsck/`` must never import
it (enforced by import-linter).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def naive_merge_query_topk(
    best_ids: NDArray[np.int64],
    best_dist: NDArray[np.float32],
    cand_ids: NDArray[np.int64],
    cand_dist: NDArray[np.float32],
    k: int,
) -> None:
    """In-place merge of one query's running top-k with a block's candidates."""
    # Collect valid entries from both sides into a small Python list — the
    # merged set is at most 2k, so clarity wins over micro-optimisation.
    merged: list[tuple[float, int]] = []
    for j in range(k):
        bid = int(best_ids[j])
        if bid >= 0:
            merged.append((float(best_dist[j]), bid))
    n_cand = int(cand_ids.shape[0])
    for j in range(n_cand):
        cid = int(cand_ids[j])
        if cid >= 0:
            merged.append((float(cand_dist[j]), cid))
    merged.sort(key=lambda t: (t[0], t[1]))
    # Deduplicate by id (same vector cannot appear twice across blocks).
    seen: list[int] = []
    unique: list[tuple[float, int]] = []
    for dist, vid in merged:
        already = False
        for s in seen:
            if s == vid:
                already = True
                break
        if already:
            continue
        seen.append(vid)
        unique.append((dist, vid))
        if len(unique) >= k:
            break
    best_ids[:] = -1
    best_dist[:] = np.float32(np.inf)
    for j, (dist, vid) in enumerate(unique):
        best_ids[j] = vid
        best_dist[j] = np.float32(dist)


def naive_block_topk_indices(
    scores_row: NDArray[np.float32],
    id_row: NDArray[np.int64],
    k: int,
) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
    """Top-k within one block for a single query; ties by ascending id."""
    b = int(scores_row.shape[0])
    take = min(k, b)
    if take == 0:
        return (
            np.full(0, -1, dtype=np.int64),
            np.full(0, np.float32(np.inf), dtype=np.float32),
        )
    if take == b:
        order = list(range(b))
    else:
        part = np.argpartition(scores_row, take - 1)[:take]
        order = [int(i) for i in part]
    order.sort(key=lambda i: (float(scores_row[i]), int(id_row[i])))
    out_ids = np.empty(take, dtype=np.int64)
    out_dist = np.empty(take, dtype=np.float32)
    for j, i in enumerate(order):
        out_ids[j] = id_row[i]
        out_dist[j] = scores_row[i]
    return out_ids, out_dist
