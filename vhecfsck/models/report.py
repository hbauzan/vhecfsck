"""Audit report types (P2-10 precursor to P3-01 pydantic schema).

Frozen dataclasses matching ``01-architecture.md`` §6 shape. No credentials,
raw vectors, or document text in any field.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vhecfsck.models.corpus import IndexCounts
from vhecfsck.models.metrics import MetricResult, Verdict, metric_result_to_dict
from vhecfsck.models.target import TargetDescriptor

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class RunContext:
    """Per-run metadata embedded in the report."""

    started_at: str
    duration_seconds: float
    seed: int
    deterministic: bool
    stage_timings: Mapping[str, float]
    host: Mapping[str, Any]


@dataclass(frozen=True)
class Report:
    """Versioned audit artifact consumed by CLI, server, and dashboards."""

    schema_version: str
    tool_version: str
    verdict: Verdict
    run: RunContext
    target: TargetDescriptor
    counts: IndexCounts
    metrics: tuple[MetricResult, ...]
    warnings: tuple[str, ...]
    config: Mapping[str, Any]
    degenerate: int = 0
    offending_vector_ids: tuple[int, ...] = field(default_factory=tuple)


def report_to_dict(report: Report) -> dict[str, Any]:
    """JSON-friendly serialisation (deterministic key order deferred to P3-02)."""
    desc = report.target
    counts = report.counts
    return {
        "schema_version": report.schema_version,
        "tool_version": report.tool_version,
        "verdict": report.verdict.value,
        "run": {
            "started_at": report.run.started_at,
            "duration_seconds": report.run.duration_seconds,
            "seed": report.run.seed,
            "deterministic": report.run.deterministic,
            "stage_timings": dict(report.run.stage_timings),
            "host": dict(report.run.host),
        },
        "target": {
            "engine": desc.engine,
            "engine_version": desc.engine_version,
            "index_kind": desc.index_kind.value,
            "index_name": desc.index_name,
            "location": desc.location,
            "dimension": desc.dimension,
            "metric_space": desc.metric_space.value,
        },
        "counts": {
            "live": counts.live,
            "deleted": counts.deleted,
            "total": counts.total,
            "indexed": counts.indexed,
            "degenerate": counts.degenerate,
            "exact": counts.exact,
            "read_at": counts.read_at.isoformat(),
        },
        "metrics": [metric_result_to_dict(m) for m in report.metrics],
        "warnings": list(report.warnings),
        "config": dict(report.config),
        "degenerate": report.degenerate,
        "offending_vector_ids": list(report.offending_vector_ids),
    }


def metric_by_id(
    report: Report,
    metric_id: str,
) -> MetricResult | None:
    """Return the first metric with ``id``, or ``None``."""
    for result in report.metrics:
        if result.id == metric_id:
            return result
    return None


def metrics_as_map(report: Report) -> dict[str, MetricResult]:
    """Index metrics by id (last wins if duplicated)."""
    out: dict[str, MetricResult] = {}
    for result in report.metrics:
        out[result.id] = result
    return out
