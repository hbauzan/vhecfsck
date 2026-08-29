"""In-memory SyntheticAdapter: exact, IVF, and IVF+tombstone post-filter.

Mechanically faithful approximate search (ADR-0014). Degradation comes only
from scanned lists and tombstone post-filtering — never from random result
corruption. Private k-means is not shared with core partition metrics.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.random import default_rng
from numpy.typing import NDArray

from vhecfsck.adapters.base import (
    FloatMatrix,
    IdArray,
    SearchParams,
    iter_vector_batches,
)
from vhecfsck.errors import UsageError
from vhecfsck.models import (
    Capabilities,
    GraphStats,
    IndexCounts,
    IndexKind,
    MetricSpace,
    PartitionStats,
    SearchResult,
    TargetDescriptor,
    VectorBatch,
)
from vhecfsck.synthetic.pathologies import CorpusState, GroundTruthAnnotation

SearchMode = Literal["exact", "ivf", "ivf_tombstoned"]

# Documented collapse triple (acceptance): mean recall_id < 0.70 under
# ivf_tombstoned with this (delete_fraction, ef_budget, nprobe) on the
# seeded corpus used by test_documented_recall_collapse_triple.
RECALL_COLLAPSE_DELETE_FRACTION: float = 0.35
RECALL_COLLAPSE_EF_BUDGET: int = 8
RECALL_COLLAPSE_NPROBE: int = 1

_ENGINE = "synthetic"
_ENGINE_VERSION = "0.1.0"
_KMEANS_ITERS = 12


class SyntheticAdapter:
    """Read-only NumPy index implementing IndexAdapter structurally."""

    def __init__(
        self,
        state: CorpusState,
        *,
        mode: SearchMode = "exact",
        n_lists: int | None = None,
        build_seed: int = 0,
        index_name: str = "default",
        location: str = "synthetic://memory",
        persist_path: Path | str | None = None,
    ) -> None:
        if mode not in ("exact", "ivf", "ivf_tombstoned"):
            msg = f"unknown search mode: {mode!r}"
            raise UsageError(msg, hint="use exact, ivf, or ivf_tombstoned")
        self._closed = False
        self._mode: SearchMode = mode
        self._build_seed = int(build_seed)
        self._index_name = index_name
        self._location = location
        self._metric = state.metric_space
        self._ids = np.ascontiguousarray(state.ids, dtype=np.int64)
        self._vectors = np.ascontiguousarray(state.vectors, dtype=np.float32)
        self._deleted = np.ascontiguousarray(state.deleted, dtype=np.bool_)
        self._annotation = state.annotation
        self._id_to_row: dict[int, int] = {
            int(self._ids[i]): i for i in range(self._ids.shape[0])
        }
        self._live_rows = np.asarray(
            [i for i in range(self._ids.shape[0]) if not bool(self._deleted[i])],
            dtype=np.int64,
        )

        dim = int(self._vectors.shape[1]) if self._vectors.size else 0
        if mode == "exact":
            self._n_lists = 0
            self._centroids = np.empty((0, dim), dtype=np.float32)
            self._cell_of = np.full(self._ids.shape[0], -1, dtype=np.int64)
            self._lists: list[NDArray[np.int64]] = []
            kind = IndexKind.FLAT
            report_partitions = False
        else:
            n_lists_i = int(n_lists) if n_lists is not None else _default_n_lists(state)
            if n_lists_i < 1:
                msg = "n_lists must be >= 1 for IVF modes"
                raise UsageError(msg)
            self._n_lists = n_lists_i
            self._centroids, self._cell_of, self._lists = _fit_ivf(
                self._vectors,
                n_lists=n_lists_i,
                seed=self._build_seed,
                metric=self._metric,
            )
            kind = IndexKind.IVF
            report_partitions = True

        self._descriptor = TargetDescriptor(
            engine=_ENGINE,
            engine_version=_ENGINE_VERSION,
            index_kind=kind,
            index_name=index_name,
            location=location,
            dimension=dim,
            metric_space=self._metric,
        )
        self._capabilities = Capabilities(
            enumerate_vectors=True,
            random_access_by_id=True,
            report_deleted_counts=True,
            deleted_counts_exact=True,
            report_partitions=report_partitions,
            partition_live_counts=report_partitions,
            report_graph_stats=False,
            search_params_settable=True,
            filtered_search=False,
        )

        if persist_path is not None:
            path = Path(persist_path)
            self.save_npz(path)

    @classmethod
    def from_npz(cls, path: Path | str) -> SyntheticAdapter:
        """Rebuild an adapter from a session ``.npz`` written by ``save_npz``."""
        data = np.load(Path(path), allow_pickle=False)
        mode = str(data["mode"][0])
        if mode not in ("exact", "ivf", "ivf_tombstoned"):
            msg = f"corrupt npz mode: {mode!r}"
            raise UsageError(msg)
        annotation = GroundTruthAnnotation(
            dfi=float(data["ann_dfi"][0]) if data["ann_dfi"][0] >= 0 else None,
            n_deleted=int(data["ann_n_deleted"][0]),
            deleted_ids=tuple(int(x) for x in data["ann_deleted_ids"]),
        )
        # Reconstruct a minimal CorpusState; partition/cluster ids unused after build.
        n = int(data["ids"].shape[0])
        state = CorpusState(
            ids=np.ascontiguousarray(data["ids"], dtype=np.int64),
            vectors=np.ascontiguousarray(data["vectors"], dtype=np.float32),
            cluster_ids=np.zeros(n, dtype=np.int64),
            deleted=np.ascontiguousarray(data["deleted"], dtype=np.bool_),
            partition_ids=np.ascontiguousarray(data["cell_of"], dtype=np.int64),
            metric_space=MetricSpace(str(data["metric"][0])),
            annotation=annotation,
        )
        adapter = cls(
            state,
            mode=mode,  # type: ignore[arg-type]
            n_lists=int(data["n_lists"][0]) or None,
            build_seed=int(data["build_seed"][0]),
            index_name=str(data["index_name"][0]),
            location=str(data["location"][0]),
        )
        # Prefer persisted IVF assignment / centroids over a rebuild (bit-exact).
        if mode != "exact":
            adapter._centroids = np.ascontiguousarray(
                data["centroids"],
                dtype=np.float32,
            )
            adapter._cell_of = np.ascontiguousarray(data["cell_of"], dtype=np.int64)
            adapter._lists = _lists_from_assignment(
                adapter._cell_of,
                adapter._n_lists,
            )
        return adapter

    def save_npz(self, path: Path | str) -> None:
        """Persist corpus + IVF build artifacts for reuse within a test session."""
        self._ensure_open()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        dfi = self._annotation.dfi
        np.savez_compressed(
            path,
            ids=self._ids,
            vectors=self._vectors,
            deleted=self._deleted,
            centroids=self._centroids,
            cell_of=self._cell_of,
            mode=np.array([self._mode]),
            n_lists=np.array([self._n_lists], dtype=np.int64),
            build_seed=np.array([self._build_seed], dtype=np.int64),
            index_name=np.array([self._index_name]),
            location=np.array([self._location]),
            metric=np.array([self._metric.value]),
            ann_dfi=np.array([-1.0 if dfi is None else float(dfi)], dtype=np.float64),
            ann_n_deleted=np.array([self._annotation.n_deleted], dtype=np.int64),
            ann_deleted_ids=np.asarray(self._annotation.deleted_ids, dtype=np.int64),
        )

    @property
    def descriptor(self) -> TargetDescriptor:
        self._ensure_open()
        return self._descriptor

    @property
    def capabilities(self) -> Capabilities:
        self._ensure_open()
        return self._capabilities

    @property
    def dimension(self) -> int:
        self._ensure_open()
        return self._descriptor.dimension

    @property
    def metric_space(self) -> MetricSpace:
        self._ensure_open()
        return self._metric

    def counts(self) -> IndexCounts:
        self._ensure_open()
        deleted = int(self._annotation.n_deleted)
        total = int(self._ids.shape[0])
        live = total - deleted
        return IndexCounts(
            live=live,
            deleted=deleted,
            total=total,
            indexed=total,
            degenerate=0,
            exact=True,
            read_at=datetime.now(tz=UTC),
        )

    def iter_live_vectors(self, *, batch_size: int) -> Iterator[VectorBatch]:
        self._ensure_open()
        live_ids = self._ids[self._live_rows]
        live_vecs = self._vectors[self._live_rows]
        return iter_vector_batches(live_ids, live_vecs, batch_size=batch_size)

    def sample_ids(self, n: int, *, seed: int) -> IdArray:
        self._ensure_open()
        live_ids = self._ids[self._live_rows]
        take = min(int(n), int(live_ids.shape[0]))
        if take == 0:
            return np.empty(0, dtype=np.int64)
        rng = default_rng(seed)
        order = rng.choice(live_ids.shape[0], size=take, replace=False)
        return np.ascontiguousarray(live_ids[order], dtype=np.int64)

    def fetch_vectors(self, ids: IdArray) -> VectorBatch:
        self._ensure_open()
        rows = np.empty(ids.shape[0], dtype=np.int64)
        for i in range(ids.shape[0]):
            key = int(ids[i])
            row = self._id_to_row.get(key)
            if row is None:
                msg = f"unknown vector id: {key}"
                raise UsageError(msg)
            rows[i] = row
        return VectorBatch(
            ids=np.ascontiguousarray(ids, dtype=np.int64),
            vectors=np.ascontiguousarray(self._vectors[rows], dtype=np.float32),
        )

    def search(
        self,
        queries: FloatMatrix,
        k: int,
        *,
        params: SearchParams,
    ) -> SearchResult:
        self._ensure_open()
        if k < 1:
            msg = "k must be >= 1"
            raise UsageError(msg)
        if not isinstance(queries, np.ndarray) or queries.dtype != np.float32:
            msg = "queries must be float32"
            raise UsageError(msg)
        if queries.ndim != 2 or queries.shape[1] != self.dimension:
            msg = "queries must have shape (q, dimension)"
            raise UsageError(msg)

        nprobe = int(params.get("nprobe", 1))
        ef_search = int(params.get("ef_search", max(k, 1)))
        exact_flag = bool(params.get("exact", False))
        effective: dict[str, object] = {
            "nprobe": nprobe,
            "ef_search": ef_search,
            "exact": exact_flag,
        }
        if "refine_factor" in params:
            effective["refine_factor"] = params["refine_factor"]

        q = int(queries.shape[0])
        out_ids = np.full((q, k), -1, dtype=np.int64)
        out_dist = np.full((q, k), np.float32(np.inf), dtype=np.float32)

        use_exact = self._mode == "exact" or exact_flag
        for qi in range(q):
            query = queries[qi]
            if use_exact:
                ids_row, dist_row = self._search_exact(query, k)
            elif self._mode == "ivf":
                ids_row, dist_row = self._search_ivf(
                    query,
                    k,
                    nprobe=nprobe,
                    live_only=True,
                )
            else:
                ids_row, dist_row = self._search_ivf_tombstoned(
                    query,
                    k,
                    nprobe=nprobe,
                    ef_budget=ef_search,
                )
            out_ids[qi] = ids_row
            out_dist[qi] = dist_row

        return SearchResult(
            ids=out_ids,
            distances=out_dist,
            effective_params=effective,
        )

    def partitions(self) -> PartitionStats | None:
        self._ensure_open()
        if not self._capabilities.report_partitions:
            return None
        sizes = np.zeros(self._n_lists, dtype=np.int64)
        for i in range(self._ids.shape[0]):
            if self._deleted[i]:
                continue
            cell = int(self._cell_of[i])
            if cell >= 0:
                sizes[cell] += np.int64(1)
        return PartitionStats(
            sizes=sizes,
            includes_deleted=False,
            n_partitions=self._n_lists,
        )

    def graph_stats(self) -> GraphStats | None:
        self._ensure_open()
        return None

    def close(self) -> None:
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            msg = "SyntheticAdapter is closed"
            raise UsageError(msg, hint="create a new adapter instance")

    def _search_exact(
        self,
        query: NDArray[np.float32],
        k: int,
    ) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
        return _topk_from_rows(
            self._vectors,
            self._ids,
            self._live_rows,
            query,
            k,
            self._metric,
        )

    def _candidate_rows(
        self,
        query: NDArray[np.float32],
        nprobe: int,
    ) -> NDArray[np.int64]:
        nprobe_i = max(1, min(int(nprobe), self._n_lists))
        cell_dists = _pairwise_distances(self._centroids, query, self._metric)
        # Ascending distance; stable by cell id.
        order = sorted(range(self._n_lists), key=lambda c: (float(cell_dists[c]), c))
        chosen = order[:nprobe_i]
        chunks: list[NDArray[np.int64]] = []
        for c in chosen:
            chunks.append(self._lists[c])
        if not chunks:
            return np.empty(0, dtype=np.int64)
        return np.concatenate(chunks)

    def _search_ivf(
        self,
        query: NDArray[np.float32],
        k: int,
        *,
        nprobe: int,
        live_only: bool,
    ) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
        rows = self._candidate_rows(query, nprobe)
        if live_only:
            rows = np.asarray(
                [int(r) for r in rows if not bool(self._deleted[int(r)])],
                dtype=np.int64,
            )
        return _topk_from_rows(
            self._vectors,
            self._ids,
            rows,
            query,
            k,
            self._metric,
        )

    def _search_ivf_tombstoned(
        self,
        query: NDArray[np.float32],
        k: int,
        *,
        nprobe: int,
        ef_budget: int,
    ) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
        """Gather top ``ef_budget`` (live+dead), drop tombstones, then top ``k``."""
        rows = self._candidate_rows(query, nprobe)
        budget = max(int(ef_budget), 1)
        cand_ids, cand_dist = _topk_from_rows(
            self._vectors,
            self._ids,
            rows,
            query,
            budget,
            self._metric,
        )
        survivors_ids: list[int] = []
        survivors_dist: list[float] = []
        for j in range(cand_ids.shape[0]):
            vid = int(cand_ids[j])
            if vid < 0:
                continue
            row = self._id_to_row[vid]
            if self._deleted[row]:
                continue
            survivors_ids.append(vid)
            survivors_dist.append(float(cand_dist[j]))
        out_ids = np.full(k, -1, dtype=np.int64)
        out_dist = np.full(k, np.float32(np.inf), dtype=np.float32)
        take = min(k, len(survivors_ids))
        for j in range(take):
            out_ids[j] = survivors_ids[j]
            out_dist[j] = np.float32(survivors_dist[j])
        return out_ids, out_dist


def _default_n_lists(state: CorpusState) -> int:
    if state.partition_ids.size == 0:
        return 1
    return int(state.partition_ids.max()) + 1


def _fit_ivf(
    vectors: NDArray[np.float32],
    *,
    n_lists: int,
    seed: int,
    metric: MetricSpace,
) -> tuple[NDArray[np.float32], NDArray[np.int64], list[NDArray[np.int64]]]:
    n = int(vectors.shape[0])
    d = int(vectors.shape[1])
    if n == 0:
        return (
            np.empty((n_lists, d), dtype=np.float32),
            np.empty(0, dtype=np.int64),
            [np.empty(0, dtype=np.int64) for _ in range(n_lists)],
        )
    rng = default_rng(seed)
    n_lists_i = min(n_lists, n)
    init_idx = rng.choice(n, size=n_lists_i, replace=False)
    centroids = np.array(vectors[init_idx], dtype=np.float32, copy=True)
    if n_lists_i < n_lists:
        # Pad unused lists with copies of the last centroid (empty after assign).
        pad = np.repeat(centroids[-1:], n_lists - n_lists_i, axis=0)
        centroids = np.concatenate([centroids, pad], axis=0)

    assignment = np.zeros(n, dtype=np.int64)
    for _ in range(_KMEANS_ITERS):
        for i in range(n):
            dists = _pairwise_distances(centroids, vectors[i], metric)
            best = 0
            best_d = float(dists[0])
            for c in range(1, n_lists):
                dc = float(dists[c])
                if dc < best_d or (dc == best_d and c < best):
                    best = c
                    best_d = dc
            assignment[i] = np.int64(best)
        # Recompute centroids from assigned rows (including deleted — index build).
        counts = np.zeros(n_lists, dtype=np.int64)
        new_c = np.zeros((n_lists, d), dtype=np.float32)
        for i in range(n):
            c = int(assignment[i])
            new_c[c] += vectors[i]
            counts[c] += np.int64(1)
        for c in range(n_lists):
            if counts[c] > 0:
                centroids[c] = new_c[c] / np.float32(counts[c])
                if metric is MetricSpace.COSINE:
                    nrm = float(np.sqrt(np.sum(centroids[c] * centroids[c])))
                    if nrm > 0:
                        centroids[c] = centroids[c] / np.float32(nrm)

    lists = _lists_from_assignment(assignment, n_lists)
    return np.ascontiguousarray(centroids, dtype=np.float32), assignment, lists


def _lists_from_assignment(
    assignment: NDArray[np.int64],
    n_lists: int,
) -> list[NDArray[np.int64]]:
    buckets: list[list[int]] = [[] for _ in range(n_lists)]
    for i in range(assignment.shape[0]):
        c = int(assignment[i])
        if 0 <= c < n_lists:
            buckets[c].append(i)
    return [np.asarray(b, dtype=np.int64) for b in buckets]


def _pairwise_distances(
    matrix: NDArray[np.float32],
    query: NDArray[np.float32],
    metric: MetricSpace,
) -> NDArray[np.float32]:
    """Distance from each row of ``matrix`` to ``query`` (lower is closer)."""
    n = int(matrix.shape[0])
    out = np.empty(n, dtype=np.float32)
    for i in range(n):
        out[i] = _distance(matrix[i], query, metric)
    return out


def _distance(
    a: NDArray[np.float32],
    b: NDArray[np.float32],
    metric: MetricSpace,
) -> np.float32:
    if metric is MetricSpace.L2:
        delta = a - b
        return np.float32(np.sqrt(np.sum(delta * delta, dtype=np.float32)))
    if metric is MetricSpace.COSINE:
        # 1 - cos; unit vectors expected from generator for COSINE.
        return np.float32(1.0) - np.float32(np.sum(a * b, dtype=np.float32))
    # DOT: rank by descending similarity → distance = -dot.
    return np.float32(-np.sum(a * b, dtype=np.float32))


def _topk_from_rows(
    vectors: NDArray[np.float32],
    ids: NDArray[np.int64],
    rows: NDArray[np.int64],
    query: NDArray[np.float32],
    k: int,
    metric: MetricSpace,
) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
    scored: list[tuple[float, int, int]] = []
    for r in rows:
        ri = int(r)
        dist = float(_distance(vectors[ri], query, metric))
        scored.append((dist, int(ids[ri]), ri))
    scored.sort(key=lambda t: (t[0], t[1]))
    out_ids = np.full(k, -1, dtype=np.int64)
    out_dist = np.full(k, np.float32(np.inf), dtype=np.float32)
    take = min(k, len(scored))
    for j in range(take):
        out_ids[j] = scored[j][1]
        out_dist[j] = np.float32(scored[j][0])
    return out_ids, out_dist
