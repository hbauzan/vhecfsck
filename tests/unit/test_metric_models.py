"""P2-01: MetricResult / MetricState / Verdict / ThresholdSpec contracts."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest
from vhecfsck.models.metrics import (
    Direction,
    EvidenceStrength,
    MetricResult,
    MetricState,
    ThresholdSpec,
    Verdict,
    metric_result_from_dict,
    metric_result_to_dict,
)


def _ok_result(**overrides: object) -> MetricResult:
    base: dict[str, object] = {
        "id": "canary_recall",
        "state": MetricState.OK,
        "value": 0.95,
        "unit": "ratio",
        "thresholds": ThresholdSpec(
            warn=0.85, fail=0.70, direction=Direction.LOWER_IS_WORSE
        ),
        "sampling": {"queries": 200, "k": 10},
        "detail": {"recall_dist": 0.95},
        "evidence_strength": EvidenceStrength.MEDIUM,
    }
    base.update(overrides)
    return MetricResult(**base)  # type: ignore[arg-type]


def test_metric_state_values() -> None:
    assert {s.value for s in MetricState} == {
        "OK",
        "WARN",
        "FAIL",
        "UNAVAILABLE",
        "DISABLED",
    }


def test_verdict_values() -> None:
    assert {v.value for v in Verdict} == {"OK", "WARN", "FAIL", "INCONCLUSIVE"}


def test_evidence_strength_values() -> None:
    assert {e.value for e in EvidenceStrength} == {"high", "medium", "low"}


def test_severity_ordering_ok_warn_fail() -> None:
    assert MetricState.OK < MetricState.WARN < MetricState.FAIL
    assert MetricState.FAIL > MetricState.WARN > MetricState.OK
    assert max(MetricState.OK, MetricState.WARN, MetricState.FAIL) is MetricState.FAIL
    assert max([MetricState.OK, MetricState.WARN]) is MetricState.WARN


def test_threshold_spec_rejects_inverted_lower_is_worse() -> None:
    with pytest.raises(ValueError, match="lower_is_worse"):
        ThresholdSpec(warn=0.70, fail=0.85, direction=Direction.LOWER_IS_WORSE)
    with pytest.raises(ValueError, match="lower_is_worse"):
        ThresholdSpec(warn=0.85, fail=0.85, direction=Direction.LOWER_IS_WORSE)


def test_threshold_spec_rejects_inverted_higher_is_worse() -> None:
    with pytest.raises(ValueError, match="higher_is_worse"):
        ThresholdSpec(warn=0.30, fail=0.15, direction=Direction.HIGHER_IS_WORSE)
    with pytest.raises(ValueError, match="higher_is_worse"):
        ThresholdSpec(warn=0.20, fail=0.20, direction=Direction.HIGHER_IS_WORSE)


def test_threshold_spec_accepts_valid_pairs() -> None:
    lo = ThresholdSpec(warn=0.85, fail=0.70, direction=Direction.LOWER_IS_WORSE)
    hi = ThresholdSpec(warn=0.15, fail=0.30, direction=Direction.HIGHER_IS_WORSE)
    assert lo.direction is Direction.LOWER_IS_WORSE
    assert hi.direction is Direction.HIGHER_IS_WORSE


def test_threshold_spec_accepts_string_direction() -> None:
    spec = ThresholdSpec(warn=0.85, fail=0.70, direction="lower_is_worse")
    assert spec.direction is Direction.LOWER_IS_WORSE


@pytest.mark.parametrize(
    "kwargs",
    [
        {"state": MetricState.UNAVAILABLE, "value": 0.0, "unavailable_reason": "x"},
        {"state": MetricState.UNAVAILABLE, "value": None, "unavailable_reason": None},
        {"state": MetricState.UNAVAILABLE, "value": None, "unavailable_reason": ""},
        {"state": MetricState.OK, "value": None},
        {"state": MetricState.WARN, "value": None},
        {"state": MetricState.FAIL, "value": None},
        {
            "state": MetricState.OK,
            "value": 1.0,
            "unavailable_reason": "should not be set",
        },
        {"state": MetricState.DISABLED, "value": 0.0},
    ],
)
def test_illegal_metric_result_combinations_raise(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _ok_result(**kwargs)


def test_legal_unavailable_and_disabled() -> None:
    u = _ok_result(
        state=MetricState.UNAVAILABLE,
        value=None,
        unavailable_reason="n_live == 0",
    )
    assert u.value is None
    d = _ok_result(state=MetricState.DISABLED, value=None, unavailable_reason=None)
    assert d.state is MetricState.DISABLED


def test_metric_result_frozen() -> None:
    r = _ok_result()
    with pytest.raises(FrozenInstanceError):
        r.value = 0.1  # type: ignore[misc]


def test_json_round_trip_without_loss() -> None:
    original = _ok_result(
        explanation="tie-tolerant canary",
        remediation_hint="raise nprobe",
        detail={"recall_id": 0.9, "ci95": [0.88, 0.92], "truncated": False},
        sampling={"queries": 200, "k": 10, "self_excluded": True},
    )
    payload = metric_result_to_dict(original)
    text = json.dumps(payload, sort_keys=True)
    restored = metric_result_from_dict(json.loads(text))
    assert restored.id == original.id
    assert restored.state is original.state
    assert restored.value == original.value
    assert restored.unit == original.unit
    assert restored.thresholds == original.thresholds
    assert dict(restored.sampling) == dict(original.sampling)
    assert dict(restored.detail) == dict(original.detail)
    assert restored.evidence_strength is original.evidence_strength
    assert restored.explanation == original.explanation
    assert restored.remediation_hint == original.remediation_hint
    assert restored.unavailable_reason == original.unavailable_reason


def test_json_round_trip_unavailable() -> None:
    original = _ok_result(
        state=MetricState.UNAVAILABLE,
        value=None,
        unavailable_reason="capability report_deleted_counts missing",
        detail={},
    )
    restored = metric_result_from_dict(metric_result_to_dict(original))
    assert restored.state is MetricState.UNAVAILABLE
    assert restored.value is None
    assert restored.unavailable_reason == original.unavailable_reason
