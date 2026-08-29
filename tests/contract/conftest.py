"""Adapter fixtures for the shared contract suite.

To add an engine: append one ``(name, factory)`` entry to ``ADAPTER_REGISTRY``.
Do not edit ``test_adapter_contract.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from vhecfsck.adapters.base import IndexAdapter
from vhecfsck.adapters.synthetic_adapter import SyntheticAdapter
from vhecfsck.models import MetricSpace
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import (
    apply_churn,
    corpus_state_from_generated,
)

AdapterFactory = Callable[[], IndexAdapter]

# Metric layer (P2+) MUST map optional-read ``None`` → UNAVAILABLE (ADR-0013).
# This constant is the suite's explicit non-skip documentation of that seam.
UNAVAILABLE_FROM_MISSING_CAPABILITY = (
    "optional IndexAdapter read returned None because the capability is False; "
    "core metrics must report UNAVAILABLE, never a substitute number"
)


def _base_state(*, n: int = 120, seed: int = 7, delete_fraction: float = 0.0):
    gen = generate_corpus(
        n,
        8,
        n_clusters=6,
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
            skew=1.0,
            seed=seed + 1,
        )
    return state


def _synthetic_exact() -> IndexAdapter:
    return SyntheticAdapter(
        _base_state(seed=11),
        mode="exact",
        index_name="contract-exact",
    )


def _synthetic_ivf() -> IndexAdapter:
    return SyntheticAdapter(
        _base_state(seed=13),
        mode="ivf",
        n_lists=6,
        build_seed=3,
        index_name="contract-ivf",
    )


def _synthetic_ivf_tombstoned() -> IndexAdapter:
    return SyntheticAdapter(
        _base_state(seed=17, delete_fraction=0.25),
        mode="ivf_tombstoned",
        n_lists=6,
        build_seed=5,
        index_name="contract-tombstoned",
    )


# Append new engines here only — the contract suite stays unmodified.
ADAPTER_REGISTRY: list[tuple[str, AdapterFactory]] = [
    ("synthetic_exact", _synthetic_exact),
    ("synthetic_ivf", _synthetic_ivf),
    ("synthetic_ivf_tombstoned", _synthetic_ivf_tombstoned),
]


_ADAPTER_NAMES = [name for name, _ in ADAPTER_REGISTRY]


@pytest.fixture(params=_ADAPTER_NAMES, ids=_ADAPTER_NAMES)
def adapter(request: pytest.FixtureRequest) -> Iterator[IndexAdapter]:
    """Parametrised open adapter; closed after each test (idempotent)."""
    factory = dict(ADAPTER_REGISTRY)[request.param]
    instance = factory()
    yield instance
    instance.close()
