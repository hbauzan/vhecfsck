"""Audit report types and Pydantic v2 schema (P3-01).

Matching ``01-architecture.md`` §6 shape. No credentials, raw vectors,
or document text in any field.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vhecfsck.models.corpus import IndexCounts
from vhecfsck.models.metrics import (
    MetricResult,
    Verdict,
    metric_result_from_dict,
    metric_result_to_dict,
)
from vhecfsck.models.target import IndexKind, MetricSpace, TargetDescriptor

# schema_version change policy (ADR-0008):
# - Additive changes (new optional fields) -> minor version bump (e.g. 1.0 -> 1.1)
# - Removals or breaking semantic changes -> major version bump (e.g. 1.0 -> 2.0)
#   plus a mandatory migration note in CHANGELOG.md.
SCHEMA_VERSION: str = "1.1"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"bearer\s+[a-zA-Z0-9._-]{20,}", re.IGNORECASE),
    re.compile(r"(?:api[-_]?key|password|secret|token)\s*=\s*[^\s'\"]+", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9._%+-]+:[a-zA-Z0-9._%+-]+@"),
)


class RunContext(BaseModel):
    """Per-run metadata embedded in the report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    started_at: str
    duration_seconds: float
    seed: int
    deterministic: bool
    stage_timings: dict[str, float]
    host: dict[str, Any]
    peak_rss_mb: float | None = None


class Report(BaseModel):
    """Versioned audit artifact consumed by CLI, server, and dashboards.

    Pydantic v2 model matching ``01-architecture.md`` §6. Enforces
    ``extra = "forbid"`` and validates that no credential secrets leak into
    report fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    schema_version: str
    tool_version: str
    verdict: Verdict
    run: RunContext
    target: TargetDescriptor
    counts: IndexCounts
    metrics: tuple[MetricResult, ...]
    warnings: tuple[str, ...]
    config: dict[str, Any]
    degenerate: int = 0
    offending_vector_ids: tuple[int, ...] = Field(default_factory=tuple)
    canary_groups: dict[str, MetricResult] | None = None
    baseline_delta: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_no_secrets(self) -> Self:
        """Reject fields containing secret tokens or credentials.

        ``redact_secrets`` rewrites passwords and query keys to the token
        ``REDACTED``. That placeholder still matches ``user:pass@`` and
        ``api_key=`` scanners, so strip it before scanning: a redacted
        ``postgres://u:REDACTED@host`` location is allowed; a live password
        is not.
        """
        serialized = str(self.model_dump_dict()).replace("REDACTED", "")
        for pat in _SECRET_PATTERNS:
            if pat.search(serialized):
                msg = (
                    "Report field contains possible credential matching pattern: "
                    f"{pat.pattern}"
                )
                raise ValueError(msg)
        return self

    def model_dump_dict(self) -> dict[str, Any]:
        """Convert Report instance to a JSON-serializable dictionary."""
        return report_to_dict(self)

    def compare(self, other: Report) -> dict[str, Any]:
        """Compare this report (baseline) against another report (current).

        Returns a structured diff dictionary suitable for baseline mode (P8).
        """
        same_schema = self.schema_version == other.schema_version
        verdict_changed = self.verdict != other.verdict
        verdict_delta = {
            "from": self.verdict.value,
            "to": other.verdict.value,
        }

        counts_delta = {
            "live": other.counts.live - self.counts.live,
            "deleted": other.counts.deleted - self.counts.deleted,
            "total": other.counts.total - self.counts.total,
            "indexed": other.counts.indexed - self.counts.indexed,
            "degenerate": other.counts.degenerate - self.counts.degenerate,
        }

        self_metrics = {m.id: m for m in self.metrics}
        other_metrics = {m.id: m for m in other.metrics}
        all_metric_ids = sorted(set(self_metrics.keys()) | set(other_metrics.keys()))

        metrics_delta: dict[str, dict[str, Any]] = {}
        for mid in all_metric_ids:
            m_self = self_metrics.get(mid)
            m_other = other_metrics.get(mid)

            v_self = m_self.value if m_self else None
            v_other = m_other.value if m_other else None
            delta = (
                (v_other - v_self)
                if (v_self is not None and v_other is not None)
                else None
            )

            metrics_delta[mid] = {
                "state_from": m_self.state.value if m_self else None,
                "state_to": m_other.state.value if m_other else None,
                "value_from": v_self,
                "value_to": v_other,
                "delta": delta,
            }

        self_warns = set(self.warnings)
        other_warns = set(other.warnings)
        warnings_diff = {
            "added": sorted(other_warns - self_warns),
            "removed": sorted(self_warns - other_warns),
        }

        return {
            "same_schema": same_schema,
            "verdict_changed": verdict_changed,
            "verdict_delta": verdict_delta,
            "counts_delta": counts_delta,
            "metrics_delta": metrics_delta,
            "warnings_diff": warnings_diff,
        }


def report_to_dict(report: Report) -> dict[str, Any]:
    """JSON-friendly serialisation matching ``01-architecture.md`` §6."""
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
        "canary_groups": (
            None
            if report.canary_groups is None
            else {
                key: metric_result_to_dict(value)
                for key, value in sorted(report.canary_groups.items())
            }
        ),
        "baseline_delta": report.baseline_delta,
    }


def report_from_dict(data: Mapping[str, Any]) -> Report:
    """Deserialize a dictionary back into a Report instance."""
    from datetime import datetime

    allowed_top_keys = {
        "schema_version",
        "tool_version",
        "verdict",
        "run",
        "target",
        "counts",
        "metrics",
        "warnings",
        "config",
        "degenerate",
        "offending_vector_ids",
        "canary_groups",
        "baseline_delta",
    }
    unknown_keys = set(data.keys()) - allowed_top_keys
    if unknown_keys:
        msg = f"Unknown top-level field(s) in report dict: {sorted(unknown_keys)}"
        raise ValueError(msg)

    run_data = data["run"]
    target_data = data["target"]
    counts_data = data["counts"]

    run = RunContext(
        started_at=str(run_data["started_at"]),
        duration_seconds=float(run_data["duration_seconds"]),
        seed=int(run_data["seed"]),
        deterministic=bool(run_data["deterministic"]),
        stage_timings=dict(run_data["stage_timings"]),
        host=dict(run_data["host"]),
        peak_rss_mb=float(run_data["peak_rss_mb"])
        if run_data.get("peak_rss_mb") is not None
        else None,
    )

    target = TargetDescriptor(
        engine=str(target_data["engine"]),
        engine_version=str(target_data["engine_version"]),
        index_kind=IndexKind(str(target_data["index_kind"])),
        index_name=str(target_data["index_name"]),
        location=str(target_data["location"]),
        dimension=int(target_data["dimension"]),
        metric_space=MetricSpace(str(target_data["metric_space"])),
    )

    counts = IndexCounts(
        live=int(counts_data["live"]),
        deleted=int(counts_data["deleted"]),
        total=int(counts_data["total"]),
        indexed=int(counts_data["indexed"]),
        degenerate=int(counts_data["degenerate"]),
        exact=bool(counts_data["exact"]),
        read_at=datetime.fromisoformat(str(counts_data["read_at"])),
    )

    metrics = tuple(metric_result_from_dict(m) for m in data["metrics"])
    warnings = tuple(str(w) for w in data.get("warnings", ()))
    config = dict(data.get("config", {}))
    degenerate = int(data.get("degenerate", 0))
    offending = tuple(int(v) for v in data.get("offending_vector_ids", ()))
    groups_raw = data.get("canary_groups")
    canary_groups: dict[str, MetricResult] | None
    if groups_raw is None:
        canary_groups = None
    else:
        if not isinstance(groups_raw, dict):
            msg = "canary_groups must be an object or null"
            raise ValueError(msg)
        canary_groups = {
            str(key): metric_result_from_dict(value)
            for key, value in groups_raw.items()
        }

    return Report(
        schema_version=str(data["schema_version"]),
        tool_version=str(data["tool_version"]),
        verdict=Verdict(str(data["verdict"])),
        run=run,
        target=target,
        counts=counts,
        metrics=metrics,
        warnings=warnings,
        config=config,
        degenerate=degenerate,
        offending_vector_ids=offending,
        canary_groups=canary_groups,
        baseline_delta=data.get("baseline_delta"),
    )


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
