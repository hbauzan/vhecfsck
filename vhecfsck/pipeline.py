"""Audit pipeline orchestration (P2-10).

Single entry point ``run_audit`` for CLI and server: validate → counts →
queries → ground truth → metrics → verdict → report.
"""

from __future__ import annotations

import os
import platform
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TypeVar

import numpy as np
from numpy.typing import NDArray

from vhecfsck import __version__
from vhecfsck.adapters.base import IndexAdapter, SearchParams
from vhecfsck.config import AuditConfig, Threshold
from vhecfsck.core.canary import CANARY_METRIC_ID, compute_canary_recall
from vhecfsck.core.fragmentation import DFI_METRIC_ID, compute_dfi
from vhecfsck.core.ground_truth import KnnResult, exact_knn
from vhecfsck.core.hubness import (
    ANTIHUB_METRIC_ID,
    HUB_SHARE_METRIC_ID,
    HubnessSource,
    compute_hubness,
)
from vhecfsck.core.partitions import PARTITION_CV_METRIC_ID, compute_partition_cv
from vhecfsck.core.verdict import aggregate, verdict_to_exit_code
from vhecfsck.errors import UsageError
from vhecfsck.models import (
    EvidenceStrength,
    IndexCounts,
    MetricResult,
    MetricSpace,
    MetricState,
    ThresholdSpec,
    VectorBatch,
)
from vhecfsck.models.report import SCHEMA_VERSION, Report, RunContext

ProgressCallback = Callable[[str, float], None]
MetricCallback = Callable[[MetricResult], None]
ExactKnnFn = Callable[..., KnnResult]
_StageT = TypeVar("_StageT")

_MAX_OFFENDING_IDS = 20
_HUBNESS_SAMPLE_SEED_OFFSET = 10_007
_BYTES_PER_VECTOR = 4


def _threshold_spec(threshold: Threshold) -> ThresholdSpec:
    return ThresholdSpec(
        warn=threshold.warn,
        fail=threshold.fail,
        direction=threshold.direction,
    )


def _deadline_remaining(
    started: float,
    max_seconds: float | None,
) -> float | None:
    if max_seconds is None:
        return None
    left = float(max_seconds) - (time.monotonic() - started)
    return max(0.0, left)


def _emit_progress(
    on_progress: ProgressCallback | None,
    stage: str,
    fraction: float,
) -> None:
    if on_progress is not None:
        on_progress(stage, min(1.0, max(0.0, fraction)))


@dataclass(frozen=True)
class _CorpusSnapshot:
    ids: NDArray[np.int64]
    vectors: NDArray[np.float32]
    live_ids: frozenset[int]


def _materialise_live_corpus(adapter: IndexAdapter) -> _CorpusSnapshot:
    ids_parts: list[NDArray[np.int64]] = []
    vec_parts: list[NDArray[np.float32]] = []
    for batch in adapter.iter_live_vectors(batch_size=4096):
        ids_parts.append(np.asarray(batch.ids, dtype=np.int64))
        vec_parts.append(np.ascontiguousarray(batch.vectors, dtype=np.float32))
    if not ids_parts:
        empty = np.asarray([], dtype=np.int64)
        return _CorpusSnapshot(
            ids=empty,
            vectors=np.zeros((0, 0), dtype=np.float32),
            live_ids=frozenset(),
        )
    ids = np.concatenate(ids_parts)
    vectors = np.concatenate(vec_parts, axis=0)
    live_ids = frozenset(int(x) for x in ids.tolist())
    return _CorpusSnapshot(ids=ids, vectors=vectors, live_ids=live_ids)


def _validate_vectors(
    snapshot: _CorpusSnapshot,
    *,
    metric_space: MetricSpace,
    dimension: int,
) -> tuple[tuple[str, ...], int, tuple[int, ...]]:
    """§1.6 validation. Returns warnings, degenerate count, offending ids."""
    warnings: list[str] = []
    offending: list[int] = []
    degenerate = 0
    n_live = int(snapshot.ids.shape[0])

    if n_live < 2:
        raise UsageError(
            f"fewer than 2 live vectors (n_live={n_live})",
            hint="An audit requires at least two live vectors.",
        )

    if snapshot.vectors.ndim != 2 or int(snapshot.vectors.shape[1]) != dimension:
        raise UsageError(
            "dimension mismatch between adapter descriptor and live vectors",
            hint="Queries and corpus must share the index dimension.",
        )

    for i in range(n_live):
        row = snapshot.vectors[i]
        if not np.all(np.isfinite(row)):
            if len(offending) < _MAX_OFFENDING_IDS:
                offending.append(int(snapshot.ids[i]))
            continue
        if metric_space is MetricSpace.COSINE:
            norm = float(np.sqrt(np.sum(row * row, dtype=np.float32)))
            if norm <= 0.0:
                degenerate += 1

    if offending:
        warnings.append(
            f"non_finite_vectors: {len(offending)} ids (cap {_MAX_OFFENDING_IDS})"
        )
        raise UsageError(
            "NaN or Inf in live corpus vectors",
            hint="Sanitise embeddings before audit; see offending_vector_ids.",
        )

    if degenerate > 0:
        warnings.append(
            f"zero_norm_cosine_vectors: {degenerate} excluded from ground truth"
        )

    return tuple(warnings), degenerate, tuple(offending)


def _degrade_sampling(
    config: AuditConfig,
    *,
    n_live: int,
    dimension: int,
) -> AuditConfig:
    """Shrink query/sample counts when ``max_memory_mb`` would be exceeded."""
    if config.max_memory_mb is None:
        return config
    budget_bytes = float(config.max_memory_mb) * 1024.0 * 1024.0
    need = float(n_live) * float(dimension) * _BYTES_PER_VECTOR
    if need <= budget_bytes:
        return config
    scale = budget_bytes / need
    new_queries = max(5, int(config.queries * scale))
    new_hub = max(1000, int(config.hubness_sample_size * scale))
    return replace(
        config,
        queries=new_queries,
        hubness_sample_size=new_hub,
    )


def _self_exclude_engine_neighbours(
    neighbour_ids: NDArray[np.int64],
    sample_ids: NDArray[np.int64],
    k_hub: int,
) -> NDArray[np.int64]:
    s = int(sample_ids.shape[0])
    out = np.full((s, k_hub), -1, dtype=np.int64)
    for qi in range(s):
        exclude = int(sample_ids[qi])
        taken = 0
        for j in range(int(neighbour_ids.shape[1])):
            nid = int(neighbour_ids[qi, j])
            if nid < 0:
                break
            if nid == exclude:
                continue
            out[qi, taken] = nid
            taken += 1
            if taken >= k_hub:
                break
    return out


def _unavailable_metric(
    metric_id: str,
    reason: str,
    *,
    config: AuditConfig,
    unit: str = "ratio",
) -> MetricResult:
    th = config.thresholds[metric_id]
    spec = _threshold_spec(th)
    return MetricResult(
        id=metric_id,
        state=MetricState.UNAVAILABLE,
        value=None,
        unit=unit,
        thresholds=spec,
        sampling={},
        detail={},
        evidence_strength=EvidenceStrength.LOW,
        unavailable_reason=reason,
    )


def _run_metric(
    metric_id: str,
    fn: Callable[[], MetricResult],
    *,
    config: AuditConfig,
    enabled: bool,
    on_metric: MetricCallback | None = None,
) -> MetricResult:
    if not enabled:
        result = MetricResult(
            id=metric_id,
            state=MetricState.DISABLED,
            value=None,
            unit="ratio",
            thresholds=_threshold_spec(config.thresholds[metric_id]),
            sampling={},
            detail={},
            evidence_strength=EvidenceStrength.LOW,
        )
    else:
        try:
            result = fn()
        except Exception as exc:
            result = _unavailable_metric(
                metric_id,
                f"{type(exc).__name__}: {exc}",
                config=config,
            )
    if on_metric is not None:
        on_metric(result)
    return result


def _collect_warnings(
    metrics: Sequence[MetricResult],
    base: Iterable[str],
) -> tuple[str, ...]:
    out: list[str] = list(base)
    for result in metrics:
        detail = result.detail
        if detail.get("snapshot_inconsistent"):
            out.append("snapshot_inconsistent")
        if detail.get("thresholds_uncalibrated_for_sample_size"):
            out.append("thresholds_uncalibrated_for_sample_size")
        if detail.get("truncated"):
            out.append(f"{result.id}: truncated")
    # Deduplicate preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for w in out:
        if w in seen:
            continue
        seen.add(w)
        unique.append(w)
    return tuple(unique)


def run_audit(
    adapter: IndexAdapter,
    config: AuditConfig,
    *,
    search_params: SearchParams | None = None,
    on_progress: ProgressCallback | None = None,
    on_metric: MetricCallback | None = None,
    exact_knn_fn: ExactKnnFn | None = None,
) -> Report:
    """Run a full audit and return a versioned :class:`Report`.

    Parameters
    ----------
    search_params:
        Engine knobs forwarded to ``adapter.search`` (IVF nprobe, etc.).
    on_metric:
        Called once per metric as soon as it resolves, so a live feed can
        paint values incrementally rather than all at once at the end.
    exact_knn_fn:
        Injectable ground-truth backend (defaults to ``exact_knn``). Tests
        may replace this to count invocations.
    """
    knn = exact_knn_fn if exact_knn_fn is not None else exact_knn
    started_wall = datetime.now(tz=UTC)
    started_mono = time.monotonic()
    timings: dict[str, float] = {}
    params: SearchParams = search_params if search_params is not None else {}
    warnings: list[str] = []

    def _stage(name: str, fn: Callable[[], _StageT]) -> _StageT:
        t0 = time.monotonic()
        out = fn()
        timings[name] = time.monotonic() - t0
        return out

    _emit_progress(on_progress, "validate", 0.0)
    descriptor = adapter.descriptor
    metric_space = descriptor.metric_space
    dimension = int(descriptor.dimension)

    counts = _stage("counts", adapter.counts)
    snapshot = _stage("corpus", lambda: _materialise_live_corpus(adapter))
    n_live = int(snapshot.ids.shape[0])

    val_warnings, degenerate, offending = _validate_vectors(
        snapshot,
        metric_space=metric_space,
        dimension=dimension,
    )
    warnings.extend(val_warnings)

    effective = _degrade_sampling(
        config,
        n_live=n_live,
        dimension=dimension,
    )
    if effective.queries != config.queries or effective.hubness_sample_size != (
        config.hubness_sample_size
    ):
        warnings.append("sampling_degraded_for_memory_budget")

    _emit_progress(on_progress, "queries", 0.1)
    query_ids = adapter.sample_ids(effective.queries, seed=effective.seed)
    query_batch = adapter.fetch_vectors(query_ids)
    if int(query_batch.vectors.shape[0]) > 0:
        qdim = int(query_batch.vectors.shape[1])
        if qdim != dimension:
            raise UsageError(
                f"query dimension {qdim} != index dimension {dimension}",
            )

    hub_sample_ids = adapter.sample_ids(
        effective.hubness_sample_size,
        seed=effective.seed + _HUBNESS_SAMPLE_SEED_OFFSET,
    )
    hub_batch = adapter.fetch_vectors(hub_sample_ids)

    deadline = _deadline_remaining(started_mono, effective.max_seconds)
    ws_mb = float(effective.block_working_set_mb)

    _emit_progress(on_progress, "ground_truth", 0.2)

    def _canary_gt() -> KnnResult:
        batches = [VectorBatch(ids=snapshot.ids, vectors=snapshot.vectors)]
        need_extra = True
        gt_k = effective.k + 1 if need_extra else effective.k
        return knn(
            batches,
            query_batch.vectors,
            gt_k,
            metric_space,
            working_set_mb=ws_mb,
            max_seconds=deadline,
            n_total=n_live,
        )

    gt_result = _stage("ground_truth", _canary_gt)
    truncated_gt = bool(gt_result.truncated)

    _emit_progress(on_progress, "canary", 0.4)

    def _canary() -> MetricResult:
        search = adapter.search(
            query_batch.vectors,
            effective.k,
            params=params,
        )
        th = effective.thresholds[CANARY_METRIC_ID]
        return compute_canary_recall(
            corpus_ids=snapshot.ids,
            corpus_vectors=snapshot.vectors,
            queries=query_batch.vectors,
            returned_ids=search.ids,
            metric_space=metric_space,
            k=effective.k,
            query_source_ids=query_ids,
            self_exclude=True,
            query_source="corpus",
            search_params=dict(params),
            working_set_mb=ws_mb,
            bootstrap_seed=effective.seed,
            live_ids_at_start=snapshot.live_ids,
            ground_truth_truncated=truncated_gt,
            warn=th.warn,
            fail=th.fail,
        )

    canary = _run_metric(
        CANARY_METRIC_ID,
        _canary,
        config=effective,
        enabled=effective.metrics_enabled.get(CANARY_METRIC_ID, True),
        on_metric=on_metric,
    )

    _emit_progress(on_progress, "hubness", 0.55)

    def _hubness_pair() -> tuple[MetricResult, MetricResult]:
        hub_source: HubnessSource = effective.hubness_source
        engine_nn: NDArray[np.int64] | None = None
        if hub_source == "engine" and int(hub_batch.vectors.shape[0]) > 0:
            eng = adapter.search(
                hub_batch.vectors,
                effective.k_hub + 1,
                params=params,
            )
            engine_nn = _self_exclude_engine_neighbours(
                eng.ids,
                hub_sample_ids,
                effective.k_hub,
            )
        share_th = effective.thresholds[HUB_SHARE_METRIC_ID]
        anti_th = effective.thresholds[ANTIHUB_METRIC_ID]
        return compute_hubness(
            corpus_ids=snapshot.ids,
            corpus_vectors=snapshot.vectors,
            sample_ids=hub_sample_ids,
            metric_space=metric_space,
            k_hub=effective.k_hub,
            hubness_source=hub_source,
            sample_size=effective.hubness_sample_size,
            sample_seed=effective.seed + _HUBNESS_SAMPLE_SEED_OFFSET,
            engine_neighbour_ids=engine_nn,
            working_set_mb=ws_mb,
            share_warn=share_th.warn,
            share_fail=share_th.fail,
            anti_warn=anti_th.warn,
            anti_fail=anti_th.fail,
        )

    hub_pair: list[tuple[MetricResult, MetricResult]] = []

    def _hubness_once() -> tuple[MetricResult, MetricResult]:
        if not hub_pair:
            hub_pair.append(_hubness_pair())
        return hub_pair[0]

    hub_share = _run_metric(
        HUB_SHARE_METRIC_ID,
        lambda: _hubness_once()[0],
        config=effective,
        enabled=effective.metrics_enabled.get(HUB_SHARE_METRIC_ID, True),
        on_metric=on_metric,
    )
    antihub = _run_metric(
        ANTIHUB_METRIC_ID,
        lambda: _hubness_once()[1],
        config=effective,
        enabled=effective.metrics_enabled.get(ANTIHUB_METRIC_ID, True),
        on_metric=on_metric,
    )

    _emit_progress(on_progress, "dfi", 0.7)

    caps = adapter.capabilities

    def _dfi() -> MetricResult:
        th = effective.thresholds[DFI_METRIC_ID]
        return compute_dfi(
            counts,
            report_deleted_counts=caps.report_deleted_counts,
            estimated=not counts.exact,
            proxy=False,
            warn=th.warn,
            fail=th.fail,
        )

    dfi = _run_metric(
        DFI_METRIC_ID,
        _dfi,
        config=effective,
        enabled=effective.metrics_enabled.get(DFI_METRIC_ID, True),
        on_metric=on_metric,
    )

    _emit_progress(on_progress, "partitions", 0.85)

    def _partitions() -> MetricResult:
        parts = adapter.partitions()
        th = effective.thresholds[PARTITION_CV_METRIC_ID]
        return compute_partition_cv(
            parts,
            applicable=caps.report_partitions,
            index_name=descriptor.index_name,
            warn=th.warn,
            fail=th.fail,
        )

    partition_cv = _run_metric(
        PARTITION_CV_METRIC_ID,
        _partitions,
        config=effective,
        enabled=effective.metrics_enabled.get(PARTITION_CV_METRIC_ID, True),
        on_metric=on_metric,
    )

    metrics = (canary, hub_share, antihub, dfi, partition_cv)
    all_warnings = _collect_warnings(metrics, warnings)

    verdict = aggregate(metrics, strict_unavailable=effective.strict_unavailable)
    _ = verdict_to_exit_code(verdict)

    duration = time.monotonic() - started_mono
    run = RunContext(
        started_at=started_wall.isoformat(),
        duration_seconds=duration,
        seed=effective.seed,
        deterministic=True,
        stage_timings=timings,
        host={
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
        },
    )

    counts_out = IndexCounts(
        live=counts.live,
        deleted=counts.deleted,
        total=counts.total,
        indexed=counts.indexed,
        degenerate=degenerate,
        exact=counts.exact,
        read_at=counts.read_at,
    )

    _emit_progress(on_progress, "done", 1.0)

    return Report(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        verdict=verdict,
        run=run,
        target=descriptor,
        counts=counts_out,
        metrics=metrics,
        warnings=all_warnings,
        config=effective.to_dict(),
        degenerate=degenerate,
        offending_vector_ids=offending,
    )
