"""Metric result types (minimal surface for P2-05; full model in P2-01).

Constructor invariants enforce ADR-0004 / CORRECTION 1: ``UNAVAILABLE`` never
carries a value, and computed states always do.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

Direction = Literal["lower_is_worse", "higher_is_worse"]


class MetricState(Enum):
    """Per-metric health state (``02-metrics-spec.md`` §1.3)."""

    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"


class EvidenceStrength(Enum):
    """Honest claim strength for a computed metric (§1.4)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class ThresholdSpec:
    """Warn/fail pair and gating direction for one metric."""

    warn: float
    fail: float
    direction: Direction

    def to_dict(self) -> dict[str, float | str]:
        """JSON-friendly embedding for reports."""
        return {
            "warn": self.warn,
            "fail": self.fail,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class MetricResult:
    """One metric outcome for the report (``02-metrics-spec.md`` §2.7 shape).

    Invariants (ADR-0004):
    - ``UNAVAILABLE`` / ``DISABLED`` → ``value is None`` and non-empty reason
      when unavailable.
    - ``OK`` / ``WARN`` / ``FAIL`` → ``value is not None``.
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
