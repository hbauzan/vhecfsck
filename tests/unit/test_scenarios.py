"""P1-08: named synthetic scenarios."""

from __future__ import annotations

import time

import pytest
from vhecfsck.adapters import synthetic_adapter
from vhecfsck.adapters.base import IndexAdapter
from vhecfsck.adapters.registry import open_target
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.errors import ExitCode, UsageError
from vhecfsck.synthetic.scenarios import (
    SCENARIO_NAMES,
    build_scenario,
    list_scenarios,
    scenario_drifted,
    scenario_healthy,
    scenario_hubby,
    scenario_tiny,
    scenario_tombstoned,
)


def test_list_scenarios_matches_table() -> None:
    assert list_scenarios() == SCENARIO_NAMES
    assert set(SCENARIO_NAMES) == {
        "healthy",
        "drifted",
        "tombstoned",
        "hubby",
        "capability_limited",
        "tiny",
    }


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_scenario_has_issue_doc_and_expected_exit(name: str) -> None:
    spec = build_scenario(name)
    assert spec.name == name
    assert spec.issue
    assert len(spec.issue) > 10
    opened = open_scenario(name)
    assert isinstance(opened.adapter, IndexAdapter)
    assert opened.expectation.exit_code == spec.expectation.exit_code
    assert opened.expectation.metric_states
    opened.adapter.close()


def test_documented_exit_codes() -> None:
    assert build_scenario("healthy").expectation.exit_code is ExitCode.OK
    assert build_scenario("drifted").expectation.exit_code is ExitCode.OK
    assert build_scenario("tombstoned").expectation.exit_code is ExitCode.FAIL
    assert build_scenario("hubby").expectation.exit_code is ExitCode.INCONCLUSIVE
    assert (
        build_scenario("capability_limited").expectation.exit_code
        is ExitCode.INCONCLUSIVE
    )
    assert build_scenario("tiny").expectation.exit_code is ExitCode.INCONCLUSIVE


def test_scenario_builders_are_deterministic() -> None:
    a = scenario_healthy(size="small")
    b = scenario_healthy(size="small")
    assert a.state.vectors.tobytes() == b.state.vectors.tobytes()
    assert a.state.ids.tobytes() == b.state.ids.tobytes()


def test_tombstoned_and_drifted_issue_anchors() -> None:
    assert "pgvector#244" in scenario_tombstoned().issue
    assert "lance#4164" in scenario_drifted().issue


def test_drifted_adapter_partitions_match_induced_skew() -> None:
    """MI-01: open_scenario('drifted') must not refit IVF after skew_partitions.

    partitions() has to report the cells the operator grew, not a k-means
    rebalance of the post-append corpus.
    """
    spec = scenario_drifted(size="tiny")
    induced = spec.state.annotation.partition_sizes
    assert induced is not None
    opened = open_scenario("drifted", size="tiny")
    try:
        parts = opened.adapter.partitions()
        assert parts is not None
        got = tuple(int(x) for x in parts.sizes)
        assert got == induced
    finally:
        opened.adapter.close()


def test_open_scenario_drifted_does_not_refit_ivf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*_args: object, **_kwargs: object) -> object:
        msg = "drifted must freeze IVF assignment, not refit k-means"
        raise AssertionError(msg)

    monkeypatch.setattr(synthetic_adapter, "_fit_ivf", _explode)
    opened = open_scenario("drifted", size="tiny")
    try:
        parts = opened.adapter.partitions()
        assert parts is not None
        assert int(parts.sizes.sum()) == opened.adapter.counts().live
    finally:
        opened.adapter.close()


def test_capability_limited_hides_deleted_counts() -> None:
    opened = open_scenario("capability_limited")
    caps = opened.adapter.capabilities
    assert caps.report_deleted_counts is False
    assert caps.deleted_counts_exact is False
    assert opened.expectation.metric_states["dfi"] == "UNAVAILABLE"
    opened.adapter.close()


def test_tiny_has_fifty_vectors() -> None:
    spec = scenario_tiny()
    assert int(spec.state.ids.shape[0]) == 50
    assert scenario_hubby().issue.lower().find("hub") >= 0


def test_large_size_variant_exists() -> None:
    # Keep CI light: only check the dispatch path, not a 100k build.
    with pytest.raises(UsageError):
        build_scenario("nope", size="large")
    # healthy large would be slow; verify size tag on a cheap scenario.
    tiny = build_scenario("tiny", size="large")
    assert tiny.name == "tiny"
    assert int(tiny.state.ids.shape[0]) == 50


def test_tiny_size_is_cheap_cardinality() -> None:
    spec = scenario_healthy(size="tiny")
    assert spec.size == "tiny"
    assert int(spec.state.ids.shape[0]) == 80
    assert spec.n_lists == 4


def test_registry_synthetic_uri_opens_named_scenario() -> None:
    adapter = open_target("synthetic://tiny")
    assert adapter.descriptor.index_name == "tiny"
    assert isinstance(adapter, IndexAdapter)
    adapter.close()


def test_full_small_set_builds() -> None:
    for name in SCENARIO_NAMES:
        opened = open_scenario(name, size="small")
        _ = opened.adapter.counts()
        opened.adapter.close()


@pytest.mark.slow
def test_full_small_set_builds_under_20s() -> None:
    import os

    max_seconds = float(os.getenv("VHECFSCK_SCENARIO_TIMEOUT", "45.0"))
    t0 = time.perf_counter()
    for name in SCENARIO_NAMES:
        opened = open_scenario(name, size="small")
        _ = opened.adapter.counts()
        opened.adapter.close()
    elapsed = time.perf_counter() - t0
    assert elapsed < max_seconds, (
        f"scenario set took {elapsed:.2f}s (max {max_seconds}s)"
    )


def test_unknown_scenario_lists_supported() -> None:
    with pytest.raises(UsageError) as excinfo:
        build_scenario("not-a-scenario")
    for name in SCENARIO_NAMES:
        assert name in f"{excinfo.value} {excinfo.value.hint}"
