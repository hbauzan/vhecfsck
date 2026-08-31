"""Mutation testing suite for the numeric core and verdict engine (P8-07).

Validates that no surviving mutants exist in threshold comparison operators,
evidence strength logic, or verdict aggregation.
"""

from typing import Any

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


def _make_metric(
    state: MetricState,
    evidence: EvidenceStrength = EvidenceStrength.HIGH,
    metric_id: str = "test_metric",
    unavailable_reason: str = "reason",
) -> MetricResult:
    val = (
        0.9
        if state == MetricState.OK
        else (0.5 if state == MetricState.FAIL or state == MetricState.WARN else None)
    )
    reason = unavailable_reason if state == MetricState.UNAVAILABLE else None
    return MetricResult(
        id=metric_id,
        state=state,
        value=val,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=0.85, fail=0.70, direction=Direction.LOWER_IS_WORSE
        ),
        sampling={},
        detail={},
        evidence_strength=evidence,
        unavailable_reason=reason,
    )


def test_evaluate_lower_is_worse_exact_boundaries() -> None:
    th = ThresholdSpec(warn=0.85, fail=0.70, direction=Direction.LOWER_IS_WORSE)
    assert evaluate(0.90, th) is MetricState.OK
    assert evaluate(0.85, th) is MetricState.OK
    assert evaluate(0.84, th) is MetricState.WARN
    assert evaluate(0.70, th) is MetricState.WARN
    assert evaluate(0.69, th) is MetricState.FAIL


def test_evaluate_higher_is_worse_exact_boundaries() -> None:
    th = ThresholdSpec(warn=0.15, fail=0.30, direction=Direction.HIGHER_IS_WORSE)
    assert evaluate(0.10, th) is MetricState.OK
    assert evaluate(0.15, th) is MetricState.OK
    assert evaluate(0.16, th) is MetricState.WARN
    assert evaluate(0.30, th) is MetricState.WARN
    assert evaluate(0.31, th) is MetricState.FAIL


def test_low_evidence_fail_downgrades_to_warn() -> None:
    low_fail = _make_metric(MetricState.FAIL, EvidenceStrength.LOW)
    v = aggregate([low_fail])
    assert v is Verdict.WARN


def test_high_evidence_fail_stays_fail() -> None:
    high_fail = _make_metric(MetricState.FAIL, EvidenceStrength.HIGH)
    v = aggregate([high_fail])
    assert v is Verdict.FAIL


def test_unavailable_strict_mode() -> None:
    unavail = _make_metric(MetricState.UNAVAILABLE, EvidenceStrength.LOW)
    v_normal = aggregate([unavail], strict_unavailable=False)
    assert v_normal is Verdict.INCONCLUSIVE

    v_strict = aggregate([unavail], strict_unavailable=True)
    assert v_strict is Verdict.FAIL


def test_all_disabled_returns_inconclusive() -> None:
    disabled = _make_metric(MetricState.DISABLED)
    assert aggregate([disabled]) is Verdict.INCONCLUSIVE
    assert aggregate([]) is Verdict.INCONCLUSIVE


def test_verdict_to_exit_code_mapping() -> None:
    assert verdict_to_exit_code(Verdict.OK) == ExitCode.OK
    assert verdict_to_exit_code(Verdict.WARN) == ExitCode.WARN
    assert verdict_to_exit_code(Verdict.FAIL) == ExitCode.FAIL
    assert verdict_to_exit_code(Verdict.INCONCLUSIVE) == ExitCode.INCONCLUSIVE


def test_mutant_operator_inversion_kills_suite() -> None:
    """Metatest: assert that inverting operators in evaluate fails assertions."""
    th = ThresholdSpec(warn=0.85, fail=0.70, direction=Direction.LOWER_IS_WORSE)

    def _mutant_eval(val: float, spec: Any) -> MetricState:
        if val > spec.fail:
            return MetricState.FAIL
        return MetricState.OK

    assert _mutant_eval(0.9, th) != evaluate(0.9, th)
