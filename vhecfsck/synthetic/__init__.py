"""Synthetic corpora and injectable pathologies (numpy + models only)."""

from vhecfsck.synthetic.generator import CorpusSpec, GeneratedCorpus, generate_corpus
from vhecfsck.synthetic.pathologies import (
    CorpusState,
    GroundTruthAnnotation,
    apply_churn,
    corpus_state_from_generated,
    inject_antihubs,
    inject_hubs,
    skew_partitions,
)
from vhecfsck.synthetic.scenarios import (
    SCENARIO_NAMES,
    ScenarioExpectation,
    ScenarioSize,
    ScenarioSpec,
    build_scenario,
    list_scenarios,
)

__all__ = [
    "SCENARIO_NAMES",
    "CorpusSpec",
    "CorpusState",
    "GeneratedCorpus",
    "GroundTruthAnnotation",
    "ScenarioExpectation",
    "ScenarioSize",
    "ScenarioSpec",
    "apply_churn",
    "build_scenario",
    "corpus_state_from_generated",
    "generate_corpus",
    "inject_antihubs",
    "inject_hubs",
    "list_scenarios",
    "skew_partitions",
]
