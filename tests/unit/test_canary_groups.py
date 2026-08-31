"""P7-03: filtered / group-by canary recall (schema 1.1)."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from vhecfsck.cli import parse_filter_option
from vhecfsck.config import AuditConfig, load_config
from vhecfsck.core.canary import compute_canary_recall
from vhecfsck.core.verdict import verdict_to_exit_code
from vhecfsck.errors import UsageError
from vhecfsck.models import (
    Capabilities,
    IndexCounts,
    IndexKind,
    MetricSpace,
    MetricState,
    SearchResult,
    TargetDescriptor,
    VectorBatch,
    Verdict,
)
from vhecfsck.models.report import SCHEMA_VERSION, metric_by_id
from vhecfsck.pipeline import run_audit


def test_schema_version_is_minor_bump() -> None:
    assert SCHEMA_VERSION == "1.1"


def test_parse_filter_option() -> None:
    assert parse_filter_option("tenant_id=t0") == ("tenant_id", "t0")
    with pytest.raises(UsageError, match="invalid --filter"):
        parse_filter_option("noequals")
    with pytest.raises(UsageError, match="invalid --filter"):
        parse_filter_option("=value")


def test_eligible_ids_restricts_ground_truth() -> None:
    """GT neighbours come only from the eligible subset."""
    ids = np.arange(6, dtype=np.int64)
    corpus = np.asarray(
        [[0, 0], [1, 0], [0, 1], [10, 0], [10, 1], [0, 10]],
        dtype=np.float32,
    )
    query = np.asarray([[0.1, 0.1]], dtype=np.float32)
    # Without a filter the nearest are 0 and 1/2; restrict to far cluster.
    # GT among {3,4,5} for this query is 3 then 5 (tie on L2, lower id first).
    returned = np.asarray([[3, 5]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={"filter": {"key": "cell", "value": "far"}},
        bootstrap_seed=1337,
        enforce_min_queries=False,
        bootstrap_resamples=50,
        eligible_ids=frozenset({3, 4, 5}),
    )
    assert result.detail["recall_id"] == 1.0
    assert result.detail["recall_dist"] == 1.0


class _TenantAdapter:
    """Exact search except one tenant, whose filtered hits are the wrong group."""

    def __init__(self) -> None:
        rng = np.random.default_rng(7)
        n_good, n_bad, dim = 80, 40, 8
        self._n = n_good + n_bad
        raw = rng.standard_normal((self._n, dim)).astype(np.float32)
        self._vectors = np.ascontiguousarray(raw)
        self._ids = np.arange(self._n, dtype=np.int64)
        self._tenant = np.array(
            ["good"] * n_good + ["bad"] * n_bad,
            dtype=object,
        )
        self._closed = False
        self._caps = Capabilities(
            enumerate_vectors=True,
            random_access_by_id=True,
            report_deleted_counts=True,
            deleted_counts_exact=True,
            report_partitions=False,
            partition_live_counts=False,
            report_graph_stats=False,
            search_params_settable=True,
            filtered_search=True,
        )

    @property
    def descriptor(self) -> TargetDescriptor:
        return TargetDescriptor(
            engine="fake-tenant",
            engine_version="test",
            index_kind=IndexKind.FLAT,
            index_name="tenants",
            location="fake://tenants",
            dimension=8,
            metric_space=MetricSpace.L2,
        )

    @property
    def capabilities(self) -> Capabilities:
        return self._caps

    @property
    def dimension(self) -> int:
        return 8

    @property
    def metric_space(self) -> MetricSpace:
        return MetricSpace.L2

    def counts(self) -> IndexCounts:
        n = self._n
        return IndexCounts(
            live=n,
            deleted=0,
            total=n,
            indexed=n,
            degenerate=0,
            exact=True,
            read_at=datetime.now(tz=UTC),
        )

    def iter_live_vectors(self, *, batch_size: int):
        yield VectorBatch(ids=self._ids, vectors=self._vectors)
        del batch_size

    def sample_ids(self, n: int, *, seed: int) -> np.ndarray:
        take = min(int(n), self._n)
        rng = np.random.default_rng(seed)
        if take == self._n:
            return np.ascontiguousarray(self._ids)
        chosen = rng.choice(self._ids, size=take, replace=False)
        return np.ascontiguousarray(chosen.astype(np.int64))

    def fetch_vectors(self, ids: np.ndarray) -> VectorBatch:
        vecs = np.stack([self._vectors[int(i)] for i in ids], axis=0)
        return VectorBatch(
            ids=np.ascontiguousarray(ids, dtype=np.int64),
            vectors=np.ascontiguousarray(vecs, dtype=np.float32),
        )

    def payload_values(self, field: str) -> dict[int, object]:
        if field != "tenant_id":
            return {}
        return {int(i): str(self._tenant[int(i)]) for i in self._ids}

    def search(self, queries: np.ndarray, k: int, *, params: dict) -> SearchResult:
        filt = params.get("filter")
        qn = int(queries.shape[0])
        out = np.full((qn, k), -1, dtype=np.int64)
        dist = np.full((qn, k), np.nan, dtype=np.float32)
        for qi in range(qn):
            pool = list(range(self._n))
            if isinstance(filt, dict):
                want = str(filt.get("value"))
                if want == "bad":
                    pool = [i for i in pool if self._tenant[i] == "good"]
                else:
                    pool = [i for i in pool if self._tenant[i] == want]
            q = queries[qi].astype(np.float64)
            scored = sorted(
                pool,
                key=lambda i: (
                    float(np.dot(self._vectors[i] - q, self._vectors[i] - q)),
                    i,
                ),
            )
            for hi, idx in enumerate(scored[:k]):
                out[qi, hi] = int(idx)
                diff = self._vectors[idx] - queries[qi]
                dist[qi, hi] = np.float32(np.sqrt(float(np.dot(diff, diff))))
        return SearchResult(ids=out, distances=dist, effective_params=dict(params))

    def partitions(self):
        return None

    def graph_stats(self):
        return None

    def close(self) -> None:
        self._closed = True


def _group_config(*, group_by: str | None = None) -> AuditConfig:
    enabled = {
        "canary_recall": True,
        "hub_share_top1pct": False,
        "antihub_fraction": False,
        "dfi": True,
        "partition_size_cv": False,
    }
    return AuditConfig(
        seed=1337,
        queries=40,
        k=10,
        hubness_sample_size=40,
        metrics_enabled=enabled,
        group_by=group_by,
    )


def test_aggregate_only_misses_bad_tenant_grouped_catches_it() -> None:
    """The P7-03 contrast: mean recall hides a tenant; group-by does not."""
    adapter = _TenantAdapter()
    try:
        aggregate_report = run_audit(adapter, _group_config())
        canary = metric_by_id(aggregate_report, "canary_recall")
        assert canary is not None
        assert canary.state is MetricState.OK
        assert aggregate_report.canary_groups is None
        assert aggregate_report.verdict is not Verdict.FAIL

        grouped_cfg = _group_config(group_by="tenant_id")
        grouped = run_audit(adapter, grouped_cfg)
        headline = metric_by_id(grouped, "canary_recall")
        assert headline is not None
        assert headline.state is MetricState.OK
        assert grouped.canary_groups is not None
        assert grouped.canary_groups["good"].state is MetricState.OK
        assert grouped.canary_groups["bad"].state is MetricState.FAIL
        assert grouped.verdict is Verdict.FAIL
        assert verdict_to_exit_code(grouped.verdict) == 2
    finally:
        adapter.close()


def test_group_by_without_filtered_search_is_ignored() -> None:
    from vhecfsck.adapters.scenarios import open_scenario

    opened = open_scenario("tiny")
    try:
        cfg = load_config(
            cli_overrides={"group_by": "tenant_id", "queries": 10, "k": 5}
        )
        report = run_audit(
            opened.adapter,
            cfg,
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
        assert "group_by_ignored_filtered_search_unsupported" in report.warnings
        assert report.canary_groups is None
        assert report.schema_version == "1.1"
    finally:
        opened.adapter.close()
