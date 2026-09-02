"""Open named synthetic scenarios as SyntheticAdapter instances.

Corpus construction lives in ``vhecfsck.synthetic.scenarios`` (layering:
synthetic ⊬ adapters). This module is the seam that materialises adapters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vhecfsck.adapters.synthetic_adapter import (
    PrebuiltIvf,
    SearchMode,
    SyntheticAdapter,
)
from vhecfsck.logging import redact_secrets
from vhecfsck.synthetic.scenarios import (
    SCENARIO_NAMES,
    ScenarioExpectation,
    ScenarioSize,
    ScenarioSpec,
    build_scenario,
    list_scenarios,
)

# Healthy / tombstoned / drifted at a given size are one deterministic IVF
# build each. TH-07 reuses PrebuiltIvf across in-process opens. Drifted is
# cached from the MI-01 freeze, never from a refit.
_IVF_CACHE_NAMES: frozenset[str] = frozenset({"healthy", "tombstoned", "drifted"})
_PREBUILT_IVF: dict[tuple[str, ScenarioSize], PrebuiltIvf] = {}


def _clear_prebuilt_ivf_cache() -> None:
    """Drop cached IVF builds. Tests pin miss→hit behaviour with this."""
    _PREBUILT_IVF.clear()


def _copy_prebuilt(ivf: PrebuiltIvf) -> PrebuiltIvf:
    return PrebuiltIvf(
        centroids=np.array(ivf.centroids, dtype=np.float32, copy=True),
        cell_of=np.array(ivf.cell_of, dtype=np.int64, copy=True),
    )


@dataclass(frozen=True)
class OpenedScenario:
    """Adapter plus the frozen expectation used by P3 exit-code tests."""

    adapter: SyntheticAdapter
    expectation: ScenarioExpectation
    spec: ScenarioSpec


def open_scenario(
    name: str,
    *,
    size: ScenarioSize = "small",
    location: str | None = None,
) -> OpenedScenario:
    """Build ``ScenarioSpec`` then open a configured ``SyntheticAdapter``."""
    spec = build_scenario(name, size=size)
    mode: SearchMode = spec.mode
    loc = redact_secrets(
        location if location is not None else f"synthetic://{spec.name}"
    )
    cache_key: tuple[str, ScenarioSize] | None = None
    prebuilt: PrebuiltIvf | None = None
    if spec.mode in ("ivf", "ivf_tombstoned") and spec.name in _IVF_CACHE_NAMES:
        cache_key = (spec.name, spec.size)
        hit = _PREBUILT_IVF.get(cache_key)
        if hit is not None:
            prebuilt = _copy_prebuilt(hit)
    adapter = SyntheticAdapter(
        spec.state,
        mode=mode,
        n_lists=spec.n_lists,
        build_seed=spec.build_seed,
        index_name=spec.name,
        location=loc,
        capabilities=spec.capabilities,
        prebuilt_ivf=prebuilt,
    )
    if cache_key is not None and cache_key not in _PREBUILT_IVF:
        _PREBUILT_IVF[cache_key] = PrebuiltIvf(
            centroids=np.array(adapter._centroids, dtype=np.float32, copy=True),
            cell_of=np.array(adapter._cell_of, dtype=np.int64, copy=True),
        )
    return OpenedScenario(
        adapter=adapter,
        expectation=spec.expectation,
        spec=spec,
    )


__all__ = [
    "SCENARIO_NAMES",
    "OpenedScenario",
    "list_scenarios",
    "open_scenario",
]
