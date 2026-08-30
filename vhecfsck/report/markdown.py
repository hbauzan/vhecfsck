"""Markdown report renderer for PR comments and job summaries (P3-07)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vhecfsck.models.metrics import MetricState

if TYPE_CHECKING:
    from vhecfsck.models.report import Report


def render_markdown(report: Report) -> str:
    """Render a Report model as GitHub Flavored Markdown."""
    lines: list[str] = []

    verdict_str = (
        report.verdict.value
        if hasattr(report.verdict, "value")
        else str(report.verdict)
    )

    verdict_emoji = {
        "OK": "🟢",
        "WARN": "🟡",
        "FAIL": "🔴",
        "INCONCLUSIVE": "⚪",
    }.get(verdict_str, "❓")

    lines.append(f"## {verdict_emoji} Vector Index Audit Report: {verdict_str}")
    lines.append("")
    lines.append("### Target Information")
    lines.append(
        f"- **Engine**: `{report.target.engine}` ({report.target.engine_version})"
    )
    kind_str = (
        report.target.index_kind.value
        if hasattr(report.target.index_kind, "value")
        else str(report.target.index_kind)
    )
    lines.append(f"- **Index**: `{report.target.index_name}` ({kind_str})")
    lines.append(f"- **Location**: `{report.target.location}`")
    space_str = (
        report.target.metric_space.value
        if hasattr(report.target.metric_space, "value")
        else str(report.target.metric_space)
    )
    lines.append(f"- **Dimension**: `{report.target.dimension}d` ({space_str})")
    lines.append(f"- **Duration**: `{report.run.duration_seconds:.2f}s`")
    lines.append("")

    lines.append("### Index Cardinality")
    lines.append(
        f"- **Live**: `{report.counts.live:,}` | **Deleted**:"
        f" `{report.counts.deleted:,}` | **Total**: `{report.counts.total:,}` |"
        f" **Exact**: `{report.counts.exact}`"
    )
    lines.append("")

    lines.append("### Audit Metrics")
    lines.append(
        "| Metric | State | Value | Unit | Thresholds (warn/fail) | Evidence |"
    )
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

    state_badge = {
        MetricState.OK: "🟢 OK",
        MetricState.WARN: "🟡 WARN",
        MetricState.FAIL: "🔴 FAIL",
        MetricState.UNAVAILABLE: "⚪ UNAVAILABLE",
        MetricState.DISABLED: "⚫ DISABLED",
    }

    for metric in report.metrics:
        badge = state_badge.get(metric.state, str(metric.state))
        val_str = f"{metric.value:.6f}" if metric.value is not None else "N/A"
        unit_str = metric.unit if metric.unit else "—"
        thresh_str = (
            f"{metric.thresholds.warn:.3f} / {metric.thresholds.fail:.3f}"
            if metric.thresholds
            else "—"
        )
        evidence_str = (
            metric.evidence_strength.value
            if hasattr(metric.evidence_strength, "value")
            else (metric.evidence_strength or "—")
        )

        lines.append(
            f"| `{metric.id}` | {badge} | `{val_str}` | {unit_str} |"
            f" `{thresh_str}` | {evidence_str} |"
        )

    if report.warnings:
        lines.append("")
        lines.append("### Warnings")
        for warning in report.warnings:
            lines.append(f"- ⚠️ {warning}")

    lines.append("")
    return "\n".join(lines)
