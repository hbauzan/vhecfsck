"""P2-10: audit pipeline orchestration."""

from __future__ import annotations

from dataclasses import replace

import pytest
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import load_config
from vhecfsck.core.canary import CANARY_METRIC_ID
from vhecfsck.core.fragmentation import DFI_METRIC_ID
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.core.hubness import ANTIHUB_METRIC_ID, HUB_SHARE_METRIC_ID
from vhecfsck.core.partitions import PARTITION_CV_METRIC_ID
from vhecfsck.core.verdict import verdict_to_exit_code
from vhecfsck.models import MetricState, Verdict
from vhecfsck.models.report import metric_by_id
from vhecfsck.pipeline import run_audit
from vhecfsck.synthetic.scenarios import SCENARIO_NAMES

SCENARIO_METRIC_TO_ID = {
    "canary_recall": CANARY_METRIC_ID,
    "hub_share": HUB_SHARE_METRIC_ID,
    "antihub_fraction": ANTIHUB_METRIC_ID,
    "dfi": DFI_METRIC_ID,
    "partition_cv": PARTITION_CV_METRIC_ID,
}


def _run_scenario(name: str) -> object:
    opened = open_scenario(name)
    try:
        cfg = load_config()
        return run_audit(
            opened.adapter,
            cfg,
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
    finally:
        opened.adapter.close()


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_scenario_verdict_and_metric_states(name: str) -> None:
    """Each P1-08 scenario matches documented verdict and per-metric states."""
    opened = open_scenario(name)
    try:
        report = run_audit(
            opened.adapter,
            load_config(),
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
        exp = opened.expectation
        assert report.verdict.value == exp.verdict
        assert verdict_to_exit_code(report.verdict) is exp.exit_code
        for key, expected_state in exp.metric_states.items():
            metric_id = SCENARIO_METRIC_TO_ID[key]
            result = metric_by_id(report, metric_id)
            assert result is not None, f"missing metric {metric_id}"
            assert result.state.value == expected_state, (
                f"{name}/{metric_id}: got {result.state.value}, want {expected_state}"
            )
    finally:
        opened.adapter.close()


def test_metric_exception_degrades_to_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected metric failure → UNAVAILABLE; audit still returns a report."""

    def boom(*_a: object, **_kw: object) -> object:
        raise RuntimeError("injected dfi failure")

    monkeypatch.setattr("vhecfsck.pipeline.compute_dfi", boom)
    opened = open_scenario("tiny")
    try:
        report = run_audit(
            opened.adapter,
            load_config(),
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
        dfi = metric_by_id(report, DFI_METRIC_ID)
        assert dfi is not None
        assert dfi.state is MetricState.UNAVAILABLE
        assert dfi.unavailable_reason is not None
        assert "injected dfi failure" in dfi.unavailable_reason
        assert report.verdict is Verdict.INCONCLUSIVE
    finally:
        opened.adapter.close()


def test_max_seconds_sets_truncated_and_still_reports() -> None:
    """Deadline exceeded → truncated flag; verdict still produced."""
    opened = open_scenario("tiny")
    try:
        cfg = replace(load_config(), max_seconds=0.0)
        report = run_audit(
            opened.adapter,
            cfg,
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
        canary = metric_by_id(report, CANARY_METRIC_ID)
        assert canary is not None
        assert canary.detail.get("truncated") is True
        assert "truncated" in report.warnings or canary.detail.get("truncated")
        allowed = (Verdict.OK, Verdict.WARN, Verdict.FAIL, Verdict.INCONCLUSIVE)
        assert report.verdict in allowed
    finally:
        opened.adapter.close()


def test_ground_truth_computed_once_via_injected_fn() -> None:
    """Canary ground-truth path invokes the injected knn backend exactly once."""
    calls = 0

    def counting(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return exact_knn(*args, **kwargs)  # type: ignore[arg-type]

    opened = open_scenario("tiny")
    try:
        cfg = replace(load_config(), hubness_source="engine")
        run_audit(
            opened.adapter,
            cfg,
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
            exact_knn_fn=counting,  # type: ignore[arg-type]
        )
        assert calls == 1
    finally:
        opened.adapter.close()


def test_corpus_materialised_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live corpus is streamed from the adapter once per audit."""
    opened = open_scenario("tiny")
    try:
        adapter = opened.adapter
        original = adapter.iter_live_vectors
        count = {"n": 0}

        def counting_iter(*, batch_size: int) -> object:
            count["n"] += 1
            return original(batch_size=batch_size)

        monkeypatch.setattr(adapter, "iter_live_vectors", counting_iter)
        run_audit(
            adapter,
            load_config(),
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
        assert count["n"] == 1
    finally:
        opened.adapter.close()


def test_report_schema_fields() -> None:
    opened = open_scenario("tiny")
    try:
        report = run_audit(
            opened.adapter,
            load_config(),
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
        assert report.schema_version == "1.0"
        assert report.tool_version
        assert report.run.stage_timings
        assert "ground_truth" in report.run.stage_timings
        assert len(report.metrics) == 5
    finally:
        opened.adapter.close()


def test_on_metric_fires_once_per_metric_as_each_resolves() -> None:
    """Live progress can paint values incrementally, not all at the end."""
    seen: list[str] = []

    def _capture(metric: object) -> None:
        seen.append(metric.id)  # type: ignore[attr-defined]

    opened = open_scenario("tiny")
    try:
        run_audit(
            opened.adapter,
            load_config(),
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
            on_metric=_capture,
        )
    finally:
        opened.adapter.close()

    assert seen == [
        CANARY_METRIC_ID,
        HUB_SHARE_METRIC_ID,
        ANTIHUB_METRIC_ID,
        DFI_METRIC_ID,
        PARTITION_CV_METRIC_ID,
    ]


def test_proxy_deleted_counts_flag_dfi_estimated() -> None:
    """Postgres-like capabilities: DFI is proxy+estimated, not exact tombstones."""
    from tests.unit.test_postgres_adapter import FakePostgres
    from vhecfsck.adapters.postgres_adapter import PostgresAdapter
    from vhecfsck.models import EvidenceStrength

    adapter = PostgresAdapter(
        "postgres://alice:s3cret@localhost:5432/vectors?table=items&column=embedding",
        connection=FakePostgres(dim=4, n=16, dead=4),
    )
    try:
        report = run_audit(
            adapter,
            load_config(),
            search_params={"nprobe": 1, "ef_search": 8},
        )
        dfi = metric_by_id(report, DFI_METRIC_ID)
        assert dfi is not None
        assert dfi.detail["proxy"] is True
        assert dfi.detail["estimated"] is True
        assert dfi.evidence_strength is EvidenceStrength.MEDIUM
    finally:
        adapter.close()


def test_entrypoint_tombstoned_escalates_dfi_to_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When graph_stats has entrypoint_tombstoned=True, DFI state becomes FAIL."""
    from unittest.mock import MagicMock

    from numpy import array, int64
    from vhecfsck.adapters.scenarios import open_scenario
    from vhecfsck.models import GraphStats

    opened = open_scenario("tiny")
    try:
        adapter = opened.adapter
        fake_stats = GraphStats(
            in_degree_histogram=array([1, 2], dtype=int64),
            entry_point_ids=array([0], dtype=int64),
            entrypoint_tombstoned=True,
        )
        # Override capabilities and graph_stats
        caps = replace(adapter.capabilities, report_graph_stats=True)
        monkeypatch.setattr(type(adapter), "capabilities", property(lambda _s: caps))
        monkeypatch.setattr(adapter, "graph_stats", MagicMock(return_value=fake_stats))

        report = run_audit(
            adapter,
            load_config(),
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
        dfi = metric_by_id(report, DFI_METRIC_ID)
        assert dfi is not None
        assert dfi.state is MetricState.FAIL
        assert dfi.detail.get("entrypoint_tombstoned") is True
    finally:
        opened.adapter.close()


def test_graph_stats_none_preserves_dfi_verdict() -> None:
    """When graph_stats is None, entrypoint_tombstoned is None."""
    from vhecfsck.adapters.scenarios import open_scenario

    opened = open_scenario("tiny")
    try:
        report = run_audit(
            opened.adapter,
            load_config(),
            search_params=opened.spec.default_search_params,  # type: ignore[arg-type]
        )
        dfi = metric_by_id(report, DFI_METRIC_ID)
        assert dfi is not None
        assert dfi.detail.get("entrypoint_tombstoned") is None
        assert dfi.state is MetricState.OK
    finally:
        opened.adapter.close()
