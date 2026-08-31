"""Baseline comparison, comparability checks, and delta gating (P8-03).

Implements ADR-0011 and roadmap/02-metrics-spec.md §3.2 comparability constraints.
All metric evaluation and gating logic lives inside core/.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from vhecfsck.config import DEFAULT_DELTA_THRESHOLDS, AuditConfig
from vhecfsck.core.verdict import aggregate, evaluate
from vhecfsck.errors import ExitCode, InconclusiveError
from vhecfsck.models import (
    Direction,
    MetricResult,
    MetricState,
    ThresholdSpec,
    Verdict,
)
from vhecfsck.models.report import Report


class GateMode(StrEnum):
    """Gating policy choice when evaluating an audit with baseline mode."""

    ABSOLUTE = "absolute"
    DELTA = "delta"
    BOTH = "both"


class NotComparableError(InconclusiveError):
    """Baseline and current audit parameters differ, preventing comparison."""

    exit_code = ExitCode.INCONCLUSIVE
    code = "not_comparable"
    default_hint = "Baseline and current audit parameters must match strictly."


_COMPARABILITY_FIELDS = (
    "seed",
    "k",
    "hubness_sample_size",
    "k_hub",
    "metric_space",
    "dimension",
    "engine",
)


def check_comparability(baseline: Report, current: Report) -> None:
    """Enforce strict comparability constraints across baseline and current reports.

    Refuses comparison and raises ``NotComparableError`` (exit 3) if any of:
    seed, k, hubness_sample_size, k_hub, metric_space, dimension, or engine differ.
    """
    base_params = _extract_comparability_params(baseline)
    curr_params = _extract_comparability_params(current)

    for field in _COMPARABILITY_FIELDS:
        val_base = base_params.get(field)
        val_curr = curr_params.get(field)
        if val_base != val_curr:
            msg = (
                f"not_comparable: parameter {field!r} differs: "
                f"baseline has {val_base!r}, current audit has {val_curr!r}"
            )
            raise NotComparableError(msg)


def _extract_comparability_params(report: Report) -> dict[str, Any]:
    """Extract standard comparability parameters from report run/target/config."""
    cfg = report.config or {}
    return {
        "seed": report.run.seed,
        "k": cfg.get("k", 10),
        "hubness_sample_size": cfg.get("hubness_sample_size", 20_000),
        "k_hub": cfg.get("k_hub", 10),
        "metric_space": report.target.metric_space.value,
        "dimension": report.target.dimension,
        "engine": report.target.engine,
    }


def worst_verdict(v1: Verdict, v2: Verdict) -> Verdict:
    """Return the worse of two verdicts (FAIL > WARN > INCONCLUSIVE > OK)."""
    priority = {
        Verdict.FAIL: 3,
        Verdict.WARN: 2,
        Verdict.INCONCLUSIVE: 1,
        Verdict.OK: 0,
    }
    return v1 if priority[v1] >= priority[v2] else v2


def evaluate_baseline_delta(
    baseline: Report,
    current: Report,
    config: AuditConfig,
    gate_mode: GateMode = GateMode.BOTH,
) -> tuple[dict[str, Any], Verdict]:
    """Compare current audit against baseline report and evaluate delta gating.

    Returns a tuple of (structured_diff_dict, final_verdict).
    """
    check_comparability(baseline, current)

    base_metrics = {m.id: m for m in baseline.metrics}
    curr_metrics = {m.id: m for m in current.metrics}
    all_metric_ids = sorted(set(base_metrics.keys()) | set(curr_metrics.keys()))

    delta_results: list[MetricResult] = []
    metrics_diff: dict[str, dict[str, Any]] = {}

    delta_threshold_map = config.delta_thresholds or DEFAULT_DELTA_THRESHOLDS

    for mid in all_metric_ids:
        m_base = base_metrics.get(mid)
        m_curr = curr_metrics.get(mid)

        v_base = m_base.value if m_base else None
        v_curr = m_curr.value if m_curr else None

        if (
            v_base is not None
            and v_curr is not None
            and m_base
            and m_curr
            and m_base.state != MetricState.DISABLED
            and m_curr.state != MetricState.DISABLED
            and m_base.state != MetricState.UNAVAILABLE
            and m_curr.state != MetricState.UNAVAILABLE
        ):
            delta_val = float(v_curr - v_base)
            delta_th = delta_threshold_map.get(mid) or DEFAULT_DELTA_THRESHOLDS.get(mid)
            if delta_th:
                th_spec = ThresholdSpec(
                    warn=delta_th.warn,
                    fail=delta_th.fail,
                    direction=Direction(delta_th.direction),
                )
                delta_state = evaluate(delta_val, th_spec)
            else:
                delta_state = MetricState.OK

            delta_metric_res = MetricResult(
                id=mid,
                state=delta_state,
                value=delta_val,
                unit=m_curr.unit,
                thresholds=ThresholdSpec(
                    warn=delta_th.warn if delta_th else 0.0,
                    fail=delta_th.fail if delta_th else 0.0,
                    direction=Direction(
                        delta_th.direction if delta_th else "higher_is_worse"
                    ),
                ),
                sampling=m_curr.sampling,
                detail=m_curr.detail,
                evidence_strength=m_curr.evidence_strength,
            )
            delta_results.append(delta_metric_res)

            metrics_diff[mid] = {
                "state_from": m_base.state.value,
                "state_to": m_curr.state.value,
                "value_from": v_base,
                "value_to": v_curr,
                "delta": delta_val,
                "delta_state": delta_state.value,
            }
        else:
            delta_val = None
            delta_state_str = "UNAVAILABLE"
            metrics_diff[mid] = {
                "state_from": m_base.state.value if m_base else None,
                "state_to": m_curr.state.value if m_curr else None,
                "value_from": v_base,
                "value_to": v_curr,
                "delta": None,
                "delta_state": delta_state_str,
            }

    delta_verdict = aggregate(
        delta_results, strict_unavailable=config.strict_unavailable
    )

    if gate_mode == GateMode.ABSOLUTE:
        final_verdict = current.verdict
    elif gate_mode == GateMode.DELTA:
        final_verdict = delta_verdict
    else:  # GateMode.BOTH
        final_verdict = worst_verdict(current.verdict, delta_verdict)

    counts_delta = {
        "live": current.counts.live - baseline.counts.live,
        "deleted": current.counts.deleted - baseline.counts.deleted,
        "total": current.counts.total - baseline.counts.total,
        "indexed": current.counts.indexed - baseline.counts.indexed,
        "degenerate": current.counts.degenerate - baseline.counts.degenerate,
    }

    diff = {
        "comparable": True,
        "gate_mode": gate_mode.value
        if isinstance(gate_mode, GateMode)
        else str(gate_mode),
        "absolute_verdict": current.verdict.value,
        "delta_verdict": delta_verdict.value,
        "final_verdict": final_verdict.value,
        "counts_delta": counts_delta,
        "metrics_delta": metrics_diff,
    }

    return diff, final_verdict
