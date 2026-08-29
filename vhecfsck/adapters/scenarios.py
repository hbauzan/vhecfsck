"""Open named synthetic scenarios as SyntheticAdapter instances.

Corpus construction lives in ``vhecfsck.synthetic.scenarios`` (layering:
synthetic ⊬ adapters). This module is the seam that materialises adapters.
"""

from __future__ import annotations

from dataclasses import dataclass

from vhecfsck.adapters.synthetic_adapter import SearchMode, SyntheticAdapter
from vhecfsck.logging import redact_secrets
from vhecfsck.synthetic.scenarios import (
    SCENARIO_NAMES,
    ScenarioExpectation,
    ScenarioSize,
    ScenarioSpec,
    build_scenario,
    list_scenarios,
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
    adapter = SyntheticAdapter(
        spec.state,
        mode=mode,
        n_lists=spec.n_lists,
        build_seed=spec.build_seed,
        index_name=spec.name,
        location=loc,
        capabilities=spec.capabilities,
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
