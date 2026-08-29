"""P1-05: SyntheticAdapter with exact / IVF / IVF-tombstone search."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from vhecfsck.adapters.base import IndexAdapter
from vhecfsck.adapters.synthetic_adapter import (
    RECALL_COLLAPSE_DELETE_FRACTION,
    RECALL_COLLAPSE_EF_BUDGET,
    RECALL_COLLAPSE_NPROBE,
    SyntheticAdapter,
)
from vhecfsck.models import IndexKind, MetricSpace
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import (
    CorpusState,
    apply_churn,
    corpus_state_from_generated,
)


def _state(
    *,
    n: int = 400,
    d: int = 8,
    n_clusters: int = 8,
    seed: int = 1,
    delete_fraction: float = 0.0,
    churn_seed: int = 9,
) -> CorpusState:
    gen = generate_corpus(
        n,
        d,
        n_clusters=n_clusters,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=seed,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    if delete_fraction > 0.0:
        state = apply_churn(
            state,
            delete_fraction=delete_fraction,
            skew=1.5,
            seed=churn_seed,
        )
    return state


def _live_row_index(state: CorpusState) -> list[int]:
    return [i for i in range(state.ids.shape[0]) if not bool(state.deleted[i])]


def _exact_topk_ids(
    state: CorpusState,
    query: np.ndarray,
    k: int,
) -> np.ndarray:
    """Brute-force live top-k by L2 (ids, ascending distance)."""
    live = _live_row_index(state)
    scored: list[tuple[float, int]] = []
    for i in live:
        delta = state.vectors[i] - query
        dist = float(np.sqrt(np.sum(delta * delta, dtype=np.float32)))
        scored.append((dist, int(state.ids[i])))
    scored.sort(key=lambda t: (t[0], t[1]))
    out = np.full(k, -1, dtype=np.int64)
    take = min(k, len(scored))
    for j in range(take):
        out[j] = scored[j][1]
    return out


def _mean_recall_id(
    adapter: SyntheticAdapter,
    state: CorpusState,
    queries: np.ndarray,
    k: int,
    *,
    params: dict[str, object],
) -> float:
    result = adapter.search(queries, k, params=params)  # type: ignore[arg-type]
    total = 0.0
    for qi in range(queries.shape[0]):
        gt = _exact_topk_ids(state, queries[qi], k)
        gt_set = {int(x) for x in gt if int(x) >= 0}
        if not gt_set:
            continue
        got = {int(x) for x in result.ids[qi] if int(x) >= 0}
        total += len(gt_set & got) / float(len(gt_set))
    return total / float(queries.shape[0])


def test_isinstance_index_adapter() -> None:
    adapter = SyntheticAdapter(_state(), mode="exact")
    assert isinstance(adapter, IndexAdapter)


def test_exact_mode_recall_is_one() -> None:
    state = _state(n=200, seed=2)
    adapter = SyntheticAdapter(state, mode="exact")
    live = _live_row_index(state)
    rng = np.random.default_rng(42)
    pick = rng.choice(len(live), size=min(40, len(live)), replace=False)
    queries = np.ascontiguousarray(
        state.vectors[[live[int(j)] for j in pick]],
        dtype=np.float32,
    )
    recall = _mean_recall_id(adapter, state, queries, k=10, params={})
    assert recall == 1.0


def test_ivf_recall_decreases_as_nprobe_decreases() -> None:
    state = _state(n=800, n_clusters=16, seed=5)
    adapter = SyntheticAdapter(state, mode="ivf", n_lists=16, build_seed=3)
    live = _live_row_index(state)
    rng = np.random.default_rng(7)
    pick = rng.choice(len(live), size=50, replace=False)
    queries = np.ascontiguousarray(
        state.vectors[[live[int(j)] for j in pick]],
        dtype=np.float32,
    )
    r1 = _mean_recall_id(adapter, state, queries, k=10, params={"nprobe": 1})
    r2 = _mean_recall_id(adapter, state, queries, k=10, params={"nprobe": 2})
    r4 = _mean_recall_id(adapter, state, queries, k=10, params={"nprobe": 4})
    r8 = _mean_recall_id(adapter, state, queries, k=10, params={"nprobe": 8})
    assert r1 <= r2 <= r4 <= r8
    assert r1 < r8


def test_ivf_tombstoned_produces_short_and_empty_returns() -> None:
    # Tombstone post-filter (gather → drop dead → top-k). Query at a deleted
    # vector's coordinates with ef_budget=1: the sole candidate is the tombstone
    # itself → empty return, while live neighbours still exist for exact GT.
    state = _state(n=600, n_clusters=8, seed=11, delete_fraction=0.5, churn_seed=13)
    adapter = SyntheticAdapter(
        state,
        mode="ivf_tombstoned",
        n_lists=8,
        build_seed=17,
    )
    deleted_rows = [i for i in range(state.ids.shape[0]) if bool(state.deleted[i])]
    assert len(deleted_rows) > 10
    live = _live_row_index(state)
    assert len(live) > 20

    # Empty: query at deleted coords, ef_budget=1 → dead self is the only candidate.
    empty_queries = np.ascontiguousarray(
        state.vectors[deleted_rows[:40]],
        dtype=np.float32,
    )
    empty_result = adapter.search(
        empty_queries,
        10,
        params={"nprobe": 1, "ef_search": 1},
    )
    empty = 0
    for qi in range(empty_queries.shape[0]):
        valid = [int(x) for x in empty_result.ids[qi] if int(x) >= 0]
        assert valid == []
        gt = _exact_topk_ids(state, empty_queries[qi], 10)
        assert any(int(x) >= 0 for x in gt)
        empty += 1
    assert empty > 0

    # Short: live queries with tiny budget < k.
    live_queries = np.ascontiguousarray(state.vectors[live[:40]], dtype=np.float32)
    short_result = adapter.search(
        live_queries,
        10,
        params={"nprobe": 1, "ef_search": 3},
    )
    deleted_set = set(state.annotation.deleted_ids)
    short = 0
    for qi in range(live_queries.shape[0]):
        valid = [int(x) for x in short_result.ids[qi] if int(x) >= 0]
        assert all(vid not in deleted_set for vid in valid)
        assert len(valid) <= 3
        if len(valid) < 10:
            short += 1
    assert short > 0


def test_documented_recall_collapse_triple() -> None:
    """Seeded (delete_fraction, ef_budget, nprobe) → mean recall_id < 0.70."""
    state = _state(
        n=600,
        n_clusters=12,
        seed=21,
        delete_fraction=RECALL_COLLAPSE_DELETE_FRACTION,
        churn_seed=23,
    )
    adapter = SyntheticAdapter(
        state,
        mode="ivf_tombstoned",
        n_lists=12,
        build_seed=29,
    )
    live = _live_row_index(state)
    rng = np.random.default_rng(31)
    pick = rng.choice(len(live), size=80, replace=False)
    queries = np.ascontiguousarray(
        state.vectors[[live[int(j)] for j in pick]],
        dtype=np.float32,
    )
    recall = _mean_recall_id(
        adapter,
        state,
        queries,
        k=10,
        params={
            "nprobe": RECALL_COLLAPSE_NPROBE,
            "ef_search": RECALL_COLLAPSE_EF_BUDGET,
        },
    )
    assert recall < 0.70


def test_capabilities_honest_and_graph_unavailable() -> None:
    adapter = SyntheticAdapter(_state(), mode="ivf", n_lists=4, build_seed=1)
    caps = adapter.capabilities
    assert caps.enumerate_vectors is True
    assert caps.random_access_by_id is True
    assert caps.report_deleted_counts is True
    assert caps.deleted_counts_exact is True
    assert caps.report_partitions is True
    assert caps.partition_live_counts is True
    assert caps.search_params_settable is True
    assert caps.report_graph_stats is False
    assert adapter.graph_stats() is None


def test_counts_match_pathology_annotations() -> None:
    state = _state(n=300, delete_fraction=0.25, churn_seed=5)
    adapter = SyntheticAdapter(state, mode="exact")
    counts = adapter.counts()
    assert counts.exact is True
    assert counts.deleted == state.annotation.n_deleted
    assert counts.live == int(state.ids.shape[0]) - state.annotation.n_deleted
    assert counts.total == int(state.ids.shape[0])
    assert counts.indexed == counts.total
    assert set(state.annotation.deleted_ids) <= {
        int(state.ids[i]) for i in range(state.ids.shape[0]) if bool(state.deleted[i])
    }


def test_ivf_index_kind_and_partitions() -> None:
    state = _state(n=200, n_clusters=4, seed=8)
    adapter = SyntheticAdapter(state, mode="ivf", n_lists=4, build_seed=2)
    assert adapter.descriptor.index_kind is IndexKind.IVF
    parts = adapter.partitions()
    assert parts is not None
    assert parts.n_partitions == 4
    assert parts.includes_deleted is False
    assert int(parts.sizes.sum()) == adapter.counts().live


def test_exact_mode_is_flat() -> None:
    adapter = SyntheticAdapter(_state(), mode="exact")
    assert adapter.descriptor.index_kind is IndexKind.FLAT


def test_npz_roundtrip(tmp_path: Path) -> None:
    state = _state(n=100, seed=4, delete_fraction=0.1)
    path = tmp_path / "corpus.npz"
    adapter = SyntheticAdapter(
        state,
        mode="ivf_tombstoned",
        n_lists=4,
        build_seed=6,
        persist_path=path,
    )
    assert path.is_file()
    loaded = SyntheticAdapter.from_npz(path)
    assert isinstance(loaded, IndexAdapter)
    assert loaded.counts().live == adapter.counts().live
    assert loaded.counts().deleted == adapter.counts().deleted
    live5 = state.vectors[_live_row_index(state)[:5]]
    q = np.ascontiguousarray(live5, dtype=np.float32)
    a = adapter.search(q, 5, params={"nprobe": 2, "ef_search": 20})
    b = loaded.search(q, 5, params={"nprobe": 2, "ef_search": 20})
    assert a.ids.tobytes() == b.ids.tobytes()


def test_close_is_idempotent_and_blocks_use() -> None:
    adapter = SyntheticAdapter(_state(n=50), mode="exact")
    adapter.close()
    adapter.close()
    try:
        adapter.counts()
        raised = False
    except Exception:
        raised = True
    assert raised
