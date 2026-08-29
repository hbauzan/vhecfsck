"""P2-09: verdict engine — exhaustive aggregation truth table."""

from __future__ import annotations

import pytest
from vhecfsck.core.verdict import aggregate, evaluate, verdict_to_exit_code
from vhecfsck.errors import ExitCode
from vhecfsck.models import (
    EvidenceStrength,
    MetricResult,
    MetricState,
    ThresholdSpec,
    Verdict,
)
from vhecfsck.models.metrics import Direction


def _result(
    state: MetricState,
    *,
    value: float | None = 0.5,
    evidence: EvidenceStrength = EvidenceStrength.MEDIUM,
    reason: str | None = None,
) -> MetricResult:
    if state is MetricState.UNAVAILABLE:
        value = None
        reason = reason or "missing"
    elif state is MetricState.DISABLED:
        value = None
        reason = None
    return MetricResult(
        id="m",
        state=state,
        value=value,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=0.85, fail=0.70, direction=Direction.LOWER_IS_WORSE
        ),
        sampling={},
        detail={},
        evidence_strength=evidence,
        unavailable_reason=reason,
    )


@pytest.mark.parametrize(
    ("value", "direction", "warn", "fail", "expected"),
    [
        (0.90, Direction.LOWER_IS_WORSE, 0.85, 0.70, MetricState.OK),
        (0.80, Direction.LOWER_IS_WORSE, 0.85, 0.70, MetricState.WARN),
        (0.60, Direction.LOWER_IS_WORSE, 0.85, 0.70, MetricState.FAIL),
        (0.10, Direction.HIGHER_IS_WORSE, 0.15, 0.30, MetricState.OK),
        (0.20, Direction.HIGHER_IS_WORSE, 0.15, 0.30, MetricState.WARN),
        (0.40, Direction.HIGHER_IS_WORSE, 0.15, 0.30, MetricState.FAIL),
    ],
)
def test_evaluate_by_direction(
    value: float,
    direction: Direction,
    warn: float,
    fail: float,
    expected: MetricState,
) -> None:
    assert (
        evaluate(value, ThresholdSpec(warn=warn, fail=fail, direction=direction))
        is expected
    )


# Exhaustive truth table: (states…, strict, expected_verdict)
# Written as a table so coverage is visibly complete (P2-09).
_AGGREGATE_CASES: list[tuple[list[MetricState], bool, Verdict]] = [
    # Empty / all disabled
    ([], False, Verdict.INCONCLUSIVE),
    ([MetricState.DISABLED], False, Verdict.INCONCLUSIVE),
    ([MetricState.DISABLED, MetricState.DISABLED], True, Verdict.INCONCLUSIVE),
    # Single computed
    ([MetricState.OK], False, Verdict.OK),
    ([MetricState.WARN], False, Verdict.WARN),
    ([MetricState.FAIL], False, Verdict.FAIL),
    ([MetricState.UNAVAILABLE], False, Verdict.INCONCLUSIVE),
    ([MetricState.UNAVAILABLE], True, Verdict.FAIL),
    # Combinations of computed
    ([MetricState.OK, MetricState.WARN], False, Verdict.WARN),
    ([MetricState.OK, MetricState.FAIL], False, Verdict.FAIL),
    ([MetricState.WARN, MetricState.FAIL], False, Verdict.FAIL),
    ([MetricState.OK, MetricState.WARN, MetricState.FAIL], False, Verdict.FAIL),
    # UNAVAILABLE floor (cannot be OK)
    ([MetricState.OK, MetricState.UNAVAILABLE], False, Verdict.INCONCLUSIVE),
    ([MetricState.WARN, MetricState.UNAVAILABLE], False, Verdict.WARN),
    ([MetricState.FAIL, MetricState.UNAVAILABLE], False, Verdict.FAIL),
    # strict_unavailable
    ([MetricState.OK, MetricState.UNAVAILABLE], True, Verdict.FAIL),
    ([MetricState.WARN, MetricState.UNAVAILABLE], True, Verdict.FAIL),
    ([MetricState.FAIL, MetricState.UNAVAILABLE], True, Verdict.FAIL),
    # DISABLED excluded
    ([MetricState.DISABLED, MetricState.OK], False, Verdict.OK),
    ([MetricState.DISABLED, MetricState.FAIL], False, Verdict.FAIL),
    ([MetricState.DISABLED, MetricState.UNAVAILABLE], False, Verdict.INCONCLUSIVE),
]


@pytest.mark.parametrize(("states", "strict", "expected"), _AGGREGATE_CASES)
def test_aggregate_truth_table(
    states: list[MetricState],
    strict: bool,
    expected: Verdict,
) -> None:
    results = [_result(s) for s in states]
    assert aggregate(results, strict_unavailable=strict) is expected


def test_low_evidence_fail_contributes_at_most_warn() -> None:
    results = [
        _result(MetricState.FAIL, evidence=EvidenceStrength.LOW),
    ]
    assert aggregate(results) is Verdict.WARN
    # With a real FAIL sibling, FAIL still wins.
    results.append(_result(MetricState.FAIL, evidence=EvidenceStrength.HIGH))
    assert aggregate(results) is Verdict.FAIL


def test_all_disabled_inconclusive_not_ok() -> None:
    results = [
        _result(MetricState.DISABLED),
        _result(MetricState.DISABLED),
    ]
    assert aggregate(results) is Verdict.INCONCLUSIVE


@pytest.mark.parametrize(
    ("verdict", "code"),
    [
        (Verdict.OK, ExitCode.OK),
        (Verdict.WARN, ExitCode.WARN),
        (Verdict.FAIL, ExitCode.FAIL),
        (Verdict.INCONCLUSIVE, ExitCode.INCONCLUSIVE),
    ],
)
def test_verdict_to_exit_code(verdict: Verdict, code: ExitCode) -> None:
    assert verdict_to_exit_code(verdict) is code
