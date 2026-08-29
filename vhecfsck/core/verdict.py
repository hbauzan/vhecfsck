"""Verdict aggregation — ``02-metrics-spec.md`` §6 (P2-09).

Maps thresholds → ``MetricState``, then ``MetricResult`` lists → ``Verdict`` /
``ExitCode``. Every branch is a production paging decision.
"""

from __future__ import annotations

from collections.abc import Sequence

from vhecfsck.errors import ExitCode
from vhecfsck.models import (
    EvidenceStrength,
    MetricResult,
    MetricState,
    ThresholdSpec,
    Verdict,
)
from vhecfsck.models.metrics import Direction


def evaluate(value: float, thresholds: ThresholdSpec) -> MetricState:
    """Derive OK/WARN/FAIL from value and direction — never per-metric branching."""
    direction = thresholds.direction
    assert isinstance(direction, Direction)
    if direction is Direction.LOWER_IS_WORSE:
        if value < thresholds.fail:
            return MetricState.FAIL
        if value < thresholds.warn:
            return MetricState.WARN
        return MetricState.OK
    # HIGHER_IS_WORSE
    if value > thresholds.fail:
        return MetricState.FAIL
    if value > thresholds.warn:
        return MetricState.WARN
    return MetricState.OK


def _contribution(result: MetricResult) -> MetricState | None:
    """State that participates in aggregation, or None if excluded.

    DISABLED is excluded. FAIL with LOW evidence contributes at most WARN
    (§1.4 / §6).
    """
    if result.state is MetricState.DISABLED:
        return None
    if result.state is MetricState.UNAVAILABLE:
        return MetricState.UNAVAILABLE
    state = result.state
    if state is MetricState.FAIL and result.evidence_strength is EvidenceStrength.LOW:
        return MetricState.WARN
    return state


def _verdict_from_worst(worst: MetricState) -> Verdict:
    if worst is MetricState.FAIL:
        return Verdict.FAIL
    if worst is MetricState.WARN:
        return Verdict.WARN
    return Verdict.OK


def aggregate(
    results: Sequence[MetricResult],
    *,
    strict_unavailable: bool = False,
) -> Verdict:
    """Aggregate metric results into an overall verdict (§6).

    Rules
    -----
    - DISABLED metrics are excluded.
    - All-DISABLED (or empty) → ``INCONCLUSIVE``.
    - LOW-evidence FAIL contributes at most WARN.
    - Any UNAVAILABLE → cannot be ``OK`` (floor ``INCONCLUSIVE``);
      with ``strict_unavailable`` UNAVAILABLE is treated as FAIL.
    - Among OK/WARN/FAIL, the worst wins.
    """
    ranked: list[MetricState] = []
    saw_unavailable = False
    saw_non_disabled = False

    for result in results:
        if result.state is not MetricState.DISABLED:
            saw_non_disabled = True
        contrib = _contribution(result)
        if contrib is None:
            continue
        if contrib is MetricState.UNAVAILABLE:
            saw_unavailable = True
            if strict_unavailable:
                ranked.append(MetricState.FAIL)
            continue
        ranked.append(contrib)

    if not saw_non_disabled:
        # Empty input or only DISABLED — nothing was checked.
        return Verdict.INCONCLUSIVE

    if not ranked:
        # Only non-strict UNAVAILABLE contributions.
        return Verdict.INCONCLUSIVE

    worst = max(ranked)
    if saw_unavailable and not strict_unavailable and worst is MetricState.OK:
        return Verdict.INCONCLUSIVE
    return _verdict_from_worst(worst)


def verdict_to_exit_code(verdict: Verdict) -> ExitCode:
    """Map overall verdict to process exit code (ADR-0004)."""
    if verdict is Verdict.OK:
        return ExitCode.OK
    if verdict is Verdict.WARN:
        return ExitCode.WARN
    if verdict is Verdict.FAIL:
        return ExitCode.FAIL
    return ExitCode.INCONCLUSIVE
