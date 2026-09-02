"""Named seeded scenarios for demos, exit-code tests, and CI canaries.

Each builder is a pure function returning a ``ScenarioSpec`` (corpus + search
config + expected verdict). Adapters open the adapter instance — ``synthetic/``
must not import ``adapters/`` (architecture §4).

Small by default (~8k vectors) so the full set builds in CI under 20 s; pass
``size="tiny"`` for cheap orchestration/determinism (~80 vectors) or
``size="large"`` for perf work (~100k). Drifted uses a smaller base before the
10x append so IVF fit stays bounded.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from vhecfsck.errors import ExitCode, UsageError
from vhecfsck.models import Capabilities, MetricSpace
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import (
    CorpusState,
    apply_churn,
    corpus_state_from_generated,
    inject_antihubs,
    inject_hubs,
    partition_centroids,
    skew_partitions,
)

ScenarioSize = Literal["tiny", "small", "large"]
SearchModeName = Literal["exact", "ivf", "ivf_tombstoned"]

SCENARIO_NAMES: tuple[str, ...] = (
    "healthy",
    "drifted",
    "tombstoned",
    "hubby",
    "capability_limited",
    "tiny",
)

# Metric IDs pinned for P2/P3 expectations (roadmap/02-metrics-spec.md).
METRIC_CANARY_RECALL = "canary_recall"
METRIC_DFI = "dfi"
METRIC_HUB_SHARE = "hub_share"
METRIC_ANTIHUB_FRACTION = "antihub_fraction"
METRIC_PARTITION_CV = "partition_cv"


@dataclass(frozen=True)
class ScenarioExpectation:
    """Documented audit outcome for a scenario (asserted in P3)."""

    exit_code: ExitCode
    verdict: str
    metric_states: dict[str, str]


@dataclass(frozen=True)
class ScenarioSpec:
    """Pure scenario payload — open via ``adapters.scenarios.open_scenario``."""

    name: str
    issue: str
    state: CorpusState
    mode: SearchModeName
    n_lists: int | None
    build_seed: int
    default_search_params: dict[str, object]
    expectation: ScenarioExpectation
    size: ScenarioSize
    capabilities: Capabilities | None = None


def _n_for(size: ScenarioSize) -> int:
    if size == "tiny":
        return 80
    if size == "large":
        return 100_000
    # ~8k keeps full-set IVF builds under the 20s CI budget (Python k-means).
    return 8_000


def _dims(size: ScenarioSize, *, high: bool = False) -> int:
    if size == "tiny":
        return 8 if not high else 16
    if high:
        return 64 if size == "small" else 128
    return 16 if size == "small" else 32


def _n_clusters(size: ScenarioSize, small: int, large: int) -> int:
    if size == "tiny":
        return min(4, small)
    if size == "large":
        return large
    return small


def list_scenarios() -> tuple[str, ...]:
    """Stable tuple of registered scenario names."""
    return SCENARIO_NAMES


def build_scenario(name: str, *, size: ScenarioSize = "small") -> ScenarioSpec:
    """Dispatch to a named scenario builder."""
    key = name.strip().lower()
    builders = {
        "healthy": scenario_healthy,
        "drifted": scenario_drifted,
        "tombstoned": scenario_tombstoned,
        "hubby": scenario_hubby,
        "capability_limited": scenario_capability_limited,
        "tiny": scenario_tiny,
    }
    builder = builders.get(key)
    if builder is None:
        supported = ", ".join(SCENARIO_NAMES)
        raise UsageError(
            f"unknown synthetic scenario {name!r}",
            hint=f"supported scenarios: {supported}",
        )
    return builder(size=size)


def scenario_healthy(*, size: ScenarioSize = "small") -> ScenarioSpec:
    """Balanced clusters, no churn, generous nprobe — healthy IVF baseline."""
    n = _n_for(size)
    d = _dims(size)
    n_clusters = _n_clusters(size, 32, 64)
    gen = generate_corpus(
        n,
        d,
        n_clusters=n_clusters,
        cluster_std=0.15,
        cluster_size_skew=0.0,
        seed=101,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    return ScenarioSpec(
        name="healthy",
        issue="control: balanced IVF with generous nprobe (no known pathology)",
        state=state,
        mode="ivf",
        n_lists=n_clusters,
        build_seed=101,
        default_search_params={"nprobe": max(8, n_clusters // 4), "ef_search": 64},
        expectation=ScenarioExpectation(
            exit_code=ExitCode.OK,
            verdict="OK",
            metric_states={
                METRIC_CANARY_RECALL: "OK",
                METRIC_DFI: "OK",
                METRIC_HUB_SHARE: "OK",
                METRIC_ANTIHUB_FRACTION: "OK",
                METRIC_PARTITION_CV: "OK",
            },
        ),
        size=size,
    )


def scenario_drifted(*, size: ScenarioSize = "small") -> ScenarioSpec:
    """10x growth into existing IVF cells without refitting — lance#4164."""
    # Start smaller: growth_factor=10 multiplies live mass; keep CI under budget.
    if size == "tiny":
        n = 80
    elif size == "small":
        n = 2_000
    else:
        n = 20_000
    d = _dims(size)
    n_clusters = _n_clusters(size, 16, 32)
    gen = generate_corpus(
        n,
        d,
        n_clusters=n_clusters,
        cluster_std=0.2,
        cluster_size_skew=0.3,
        seed=202,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    # Fit-time partitions = cluster ids. Freeze those centroids before the
    # append so open_scenario does not refit k-means and erase the skew.
    state = replace(state, frozen_centroids=partition_centroids(state))
    state = skew_partitions(state, seed=203, growth_factor=10.0)
    return ScenarioSpec(
        name="drifted",
        issue="lance#4164: append into existing IVF cells without centroid refit",
        state=state,
        mode="ivf",
        n_lists=n_clusters,
        build_seed=202,
        default_search_params={"nprobe": 2, "ef_search": 32},
        expectation=ScenarioExpectation(
            exit_code=ExitCode.OK,
            verdict="OK",
            metric_states={
                METRIC_CANARY_RECALL: "OK",
                METRIC_DFI: "OK",
                METRIC_HUB_SHARE: "OK",
                METRIC_ANTIHUB_FRACTION: "OK",
                METRIC_PARTITION_CV: "OK",
            },
        ),
        size=size,
    )


def scenario_tombstoned(*, size: ScenarioSize = "small") -> ScenarioSpec:
    """35% skewed churn + tight ef_budget tombstone post-filter — pgvector#244."""
    n = _n_for(size)
    d = _dims(size)
    n_clusters = _n_clusters(size, 16, 32)
    gen = generate_corpus(
        n,
        d,
        n_clusters=n_clusters,
        cluster_std=0.2,
        cluster_size_skew=0.5,
        seed=303,
        metric_space=MetricSpace.L2,
    )
    state = apply_churn(
        corpus_state_from_generated(gen),
        delete_fraction=0.35,
        skew=2.0,
        seed=304,
    )
    return ScenarioSpec(
        name="tombstoned",
        issue="pgvector#244: tombstone post-filter path blocking under tight ef_budget",
        state=state,
        mode="ivf_tombstoned",
        n_lists=n_clusters,
        build_seed=303,
        default_search_params={"nprobe": 1, "ef_search": 8},
        expectation=ScenarioExpectation(
            exit_code=ExitCode.FAIL,
            verdict="FAIL",
            metric_states={
                METRIC_CANARY_RECALL: "FAIL",
                METRIC_DFI: "FAIL",
                METRIC_HUB_SHARE: "OK",
                METRIC_ANTIHUB_FRACTION: "OK",
                METRIC_PARTITION_CV: "OK",
            },
        ),
        size=size,
    )


def scenario_hubby(*, size: ScenarioSize = "small") -> ScenarioSpec:
    """High-d hubs and isolated outliers — hubness pathology for hub metrics."""
    n = _n_for(size)
    d = _dims(size, high=True)
    n_clusters = _n_clusters(size, 24, 48)
    gen = generate_corpus(
        n,
        d,
        n_clusters=n_clusters,
        cluster_std=0.1,
        cluster_size_skew=0.0,
        seed=404,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    n_hubs = {"tiny": 2, "small": 8, "large": 16}[size]
    state = inject_hubs(state, n_hubs=n_hubs, strength=4.0, seed=405)
    state = inject_antihubs(
        state,
        n_antihubs={"tiny": 4, "small": 20, "large": 40}[size],
        distance_factor=8.0,
        seed=406,
    )
    return ScenarioSpec(
        name="hubby",
        issue="hubness: cannibalising hubs + isolated anti-hubs in high-d space",
        state=state,
        mode="exact",
        n_lists=None,
        build_seed=404,
        default_search_params={"exact": True},
        expectation=ScenarioExpectation(
            exit_code=ExitCode.INCONCLUSIVE,
            verdict="INCONCLUSIVE",
            metric_states={
                METRIC_CANARY_RECALL: "OK",
                METRIC_DFI: "OK",
                METRIC_HUB_SHARE: "OK",
                METRIC_ANTIHUB_FRACTION: "OK",
                METRIC_PARTITION_CV: "UNAVAILABLE",
            },
        ),
        size=size,
    )


def scenario_capability_limited(*, size: ScenarioSize = "small") -> ScenarioSpec:
    """Adapter hides deleted counts — DFI must be UNAVAILABLE (INCONCLUSIVE)."""
    n = min(2_000, _n_for(size))
    d = _dims(size)
    gen = generate_corpus(
        n,
        d,
        n_clusters=_n_clusters(size, 8, 8),
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=505,
        metric_space=MetricSpace.L2,
    )
    state = apply_churn(
        corpus_state_from_generated(gen),
        delete_fraction=0.2,
        skew=0.0,
        seed=506,
    )
    caps = Capabilities(
        enumerate_vectors=True,
        random_access_by_id=True,
        report_deleted_counts=False,
        deleted_counts_exact=False,
        report_partitions=False,
        partition_live_counts=False,
        report_graph_stats=False,
        search_params_settable=True,
        filtered_search=False,
    )
    return ScenarioSpec(
        name="capability_limited",
        issue="capability honesty: missing deleted-count telemetry → DFI UNAVAILABLE",
        state=state,
        mode="exact",
        n_lists=None,
        build_seed=505,
        default_search_params={"exact": True},
        expectation=ScenarioExpectation(
            exit_code=ExitCode.INCONCLUSIVE,
            verdict="INCONCLUSIVE",
            metric_states={
                METRIC_CANARY_RECALL: "OK",
                METRIC_DFI: "UNAVAILABLE",
                METRIC_HUB_SHARE: "OK",
                METRIC_ANTIHUB_FRACTION: "OK",
                METRIC_PARTITION_CV: "UNAVAILABLE",
            },
        ),
        size=size,
        capabilities=caps,
    )


def scenario_tiny(*, size: ScenarioSize = "small") -> ScenarioSpec:
    """Fifty vectors — below hubness/recall guards → metrics UNAVAILABLE."""
    del size  # tiny is fixed cardinality by definition
    gen = generate_corpus(
        50,
        8,
        n_clusters=5,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=606,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    return ScenarioSpec(
        name="tiny",
        issue="guard floor: |S|=50 below hubness/canary sample guards",
        state=state,
        mode="exact",
        n_lists=None,
        build_seed=606,
        default_search_params={"exact": True},
        expectation=ScenarioExpectation(
            exit_code=ExitCode.INCONCLUSIVE,
            verdict="INCONCLUSIVE",
            metric_states={
                METRIC_CANARY_RECALL: "OK",
                METRIC_DFI: "OK",
                METRIC_HUB_SHARE: "UNAVAILABLE",
                METRIC_ANTIHUB_FRACTION: "UNAVAILABLE",
                METRIC_PARTITION_CV: "UNAVAILABLE",
            },
        ),
        size="small",
    )
