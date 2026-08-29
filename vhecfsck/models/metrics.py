"""Metric result types and verdict model (P2-01).

Constructor invariants enforce ADR-0004 / CORRECTION 1: ``UNAVAILABLE`` never
carries a value, and computed states always do.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Direction(Enum):
    """Threshold gating direction (``02-metrics-spec.md`` §1.5)."""

    LOWER_IS_WORSE = "lower_is_worse"
    HIGHER_IS_WORSE = "higher_is_worse"


class MetricState(Enum):
    """Per-metric health state (``02-metrics-spec.md`` §1.3)."""

    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"

    @property
    def severity(self) -> int:
        """Comparable rank for ``OK < WARN < FAIL`` aggregation (§6).

        ``UNAVAILABLE`` and ``DISABLED`` are not part of this ladder — verdict
        rules that involve them live in P2-09.
        """
        if self is MetricState.OK:
            return 0
        if self is MetricState.WARN:
            return 1
        if self is MetricState.FAIL:
            return 2
        msg = f"{self.value} has no severity rank for OK/WARN/FAIL ordering"
        raise ValueError(msg)

    def __lt__(self, other: object) -> bool:
        """Severity less-than for OK/WARN/FAIL aggregation."""
        if not isinstance(other, MetricState):
            return NotImplemented
        return self.severity < other.severity

    def __le__(self, other: object) -> bool:
        """Severity less-or-equal for OK/WARN/FAIL aggregation."""
        if not isinstance(other, MetricState):
            return NotImplemented
        return self.severity <= other.severity

    def __gt__(self, other: object) -> bool:
        """Severity greater-than for OK/WARN/FAIL aggregation."""
        if not isinstance(other, MetricState):
            return NotImplemented
        return self.severity > other.severity

    def __ge__(self, other: object) -> bool:
        """Severity greater-or-equal for OK/WARN/FAIL aggregation."""
        if not isinstance(other, MetricState):
            return NotImplemented
        return self.severity >= other.severity


class Verdict(Enum):
    """Overall audit outcome (``02-metrics-spec.md`` §6)."""

    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvidenceStrength(Enum):
    """Honest claim strength for a computed metric (§1.4)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def _coerce_direction(direction: Direction | str) -> Direction:
    if isinstance(direction, Direction):
        return direction
    try:
        return Direction(direction)
    except ValueError as exc:
        msg = f"unknown threshold direction: {direction!r}"
        raise ValueError(msg) from exc


@dataclass(frozen=True)
class ThresholdSpec:
    """Warn/fail pair and gating direction for one metric."""

    warn: float
    fail: float
    direction: Direction | str

    def __post_init__(self) -> None:
        """Coerce direction and reject inverted warn/fail pairs."""
        object.__setattr__(self, "direction", _coerce_direction(self.direction))
        direction = self.direction
        assert isinstance(direction, Direction)
        if direction is Direction.LOWER_IS_WORSE:
            if not (self.warn > self.fail):
                msg = (
                    "lower_is_worse requires warn > fail "
                    f"(got warn={self.warn}, fail={self.fail})"
                )
                raise ValueError(msg)
            return
        if direction is Direction.HIGHER_IS_WORSE:
            if not (self.warn < self.fail):
                msg = (
                    "higher_is_worse requires warn < fail "
                    f"(got warn={self.warn}, fail={self.fail})"
                )
                raise ValueError(msg)
            return
        msg = f"unknown threshold direction: {direction!r}"
        raise ValueError(msg)

    def to_dict(self) -> dict[str, float | str]:
        """JSON-friendly embedding for reports."""
        direction = self.direction
        assert isinstance(direction, Direction)
        return {
            "warn": self.warn,
            "fail": self.fail,
            "direction": direction.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ThresholdSpec:
        """Inverse of :meth:`to_dict`."""
        return cls(
            warn=float(data["warn"]),
            fail=float(data["fail"]),
            direction=str(data["direction"]),
        )


@dataclass(frozen=True)
class MetricResult:
    """One metric outcome for the report (``02-metrics-spec.md`` §2.7 shape).

    Invariants (ADR-0004):
    - ``UNAVAILABLE`` → ``value is None`` and non-empty ``unavailable_reason``.
    - ``DISABLED`` → ``value is None``.
    - ``OK`` / ``WARN`` / ``FAIL`` → ``value is not None``, no reason.
    """

    id: str
    state: MetricState
    value: float | None
    unit: str
    thresholds: ThresholdSpec
    sampling: Mapping[str, Any]
    detail: Mapping[str, Any]
    evidence_strength: EvidenceStrength
    explanation: str = ""
    remediation_hint: str = ""
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        """Reject illegal state/value/reason combinations."""
        object.__setattr__(self, "sampling", dict(self.sampling))
        object.__setattr__(self, "detail", dict(self.detail))
        if self.state is MetricState.UNAVAILABLE:
            if self.value is not None:
                msg = "UNAVAILABLE MetricResult must not carry a value"
                raise ValueError(msg)
            if not self.unavailable_reason:
                msg = "UNAVAILABLE MetricResult requires unavailable_reason"
                raise ValueError(msg)
            return
        if self.state is MetricState.DISABLED:
            if self.value is not None:
                msg = "DISABLED MetricResult must not carry a value"
                raise ValueError(msg)
            return
        if self.state in (MetricState.OK, MetricState.WARN, MetricState.FAIL):
            if self.value is None:
                msg = f"{self.state.value} MetricResult requires a value"
                raise ValueError(msg)
            if self.unavailable_reason is not None:
                msg = f"{self.state.value} MetricResult must not set unavailable_reason"
                raise ValueError(msg)
            return
        msg = f"unknown MetricState: {self.state!r}"
        raise ValueError(msg)


def metric_result_to_dict(result: MetricResult) -> dict[str, Any]:
    """Serialize a ``MetricResult`` to a JSON-friendly dict."""
    return {
        "id": result.id,
        "state": result.state.value,
        "value": result.value,
        "unit": result.unit,
        "thresholds": result.thresholds.to_dict(),
        "sampling": dict(result.sampling),
        "detail": dict(result.detail),
        "evidence_strength": result.evidence_strength.value,
        "explanation": result.explanation,
        "remediation_hint": result.remediation_hint,
        "unavailable_reason": result.unavailable_reason,
    }


def metric_result_from_dict(data: Mapping[str, Any]) -> MetricResult:
    """Deserialize a ``MetricResult`` from :func:`metric_result_to_dict` output."""
    reason = data.get("unavailable_reason")
    return MetricResult(
        id=str(data["id"]),
        state=MetricState(str(data["state"])),
        value=None if data["value"] is None else float(data["value"]),
        unit=str(data["unit"]),
        thresholds=ThresholdSpec.from_dict(data["thresholds"]),
        sampling=dict(data["sampling"]),
        detail=dict(data["detail"]),
        evidence_strength=EvidenceStrength(str(data["evidence_strength"])),
        explanation=str(data.get("explanation", "")),
        remediation_hint=str(data.get("remediation_hint", "")),
        unavailable_reason=None if reason is None else str(reason),
    )
