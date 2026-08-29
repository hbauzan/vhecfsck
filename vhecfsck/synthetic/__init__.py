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

__all__ = [
    "CorpusSpec",
    "CorpusState",
    "GeneratedCorpus",
    "GroundTruthAnnotation",
    "apply_churn",
    "corpus_state_from_generated",
    "generate_corpus",
    "inject_antihubs",
    "inject_hubs",
    "skew_partitions",
]
