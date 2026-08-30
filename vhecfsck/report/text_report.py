"""Rich terminal renderer for audit reports (P3-03).

Provides human-readable output for operators in the console with target identity,
verdict banner, cardinality counts, metrics table, metric explanations/hints, and
warnings. When ``color=False``, no ANSI escape sequences are emitted.
"""

from __future__ import annotations

from vhecfsck.models.metrics import Direction, MetricResult, MetricState, Verdict
from vhecfsck.models.report import Report


class _Colors:
    """ANSI color code constants."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    BOLD_GREEN = "\033[1;32m"
    BOLD_YELLOW = "\033[1;33m"
    BOLD_RED = "\033[1;31m"
    BOLD_MAGENTA = "\033[1;35m"
    BOLD_CYAN = "\033[1;36m"


def _verdict_color(verdict: Verdict) -> str:
    if verdict is Verdict.OK:
        return _Colors.BOLD_GREEN
    if verdict is Verdict.WARN:
        return _Colors.BOLD_YELLOW
    if verdict is Verdict.FAIL:
        return _Colors.BOLD_RED
    return _Colors.BOLD_MAGENTA


def _state_color(state: MetricState) -> str:
    if state is MetricState.OK:
        return _Colors.GREEN
    if state is MetricState.WARN:
        return _Colors.YELLOW
    if state is MetricState.FAIL:
        return _Colors.RED
    if state is MetricState.UNAVAILABLE:
        return _Colors.CYAN
    return _Colors.DIM


def _format_thresholds(m: MetricResult) -> str:
    dir_val = (
        m.thresholds.direction.value
        if isinstance(m.thresholds.direction, Direction)
        else str(m.thresholds.direction)
    )
    direction_symbol = ">" if dir_val == "lower_is_worse" else "<"
    return f"{direction_symbol} {m.thresholds.warn:.3f} / {m.thresholds.fail:.3f}"


def _format_value(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.6f}"


def render_terminal(report: Report, color: bool = True) -> str:
    """Render an Audit Report for rich human-readable terminal output.

    Args:
        report: Audit report model instance to display.
        color: Whether to include ANSI escape sequences for color formatting.

    Returns:
        Formatted terminal output text string.
    """
    lines: list[str] = []

    def c(text: str, color_code: str) -> str:
        if not color:
            return text
        return f"{color_code}{text}{_Colors.RESET}"

    # 1. Target Identity Header
    t = report.target
    r = report.run
    lines.append(c("=" * 80, _Colors.DIM))
    lines.append(c(" AUDIT TARGET IDENTITY", _Colors.BOLD))
    lines.append(c("=" * 80, _Colors.DIM))
    lines.append(f"  Engine       : {t.engine} (v{t.engine_version})")
    lines.append(f"  Index        : {t.index_name} (kind: {t.index_kind.value})")
    lines.append(f"  Location     : {t.location}")
    lines.append(f"  Dimension    : {t.dimension}d ({t.metric_space.value})")
    dur_str = f"{r.duration_seconds:.2f}s"
    lines.append(
        f"  Started At   : {r.started_at} (duration: {dur_str}, seed: {r.seed})"
    )
    lines.append("")

    # 2. Overall Verdict Banner
    v_str = report.verdict.value
    v_colored = c(f" AUDIT VERDICT: {v_str} ", _verdict_color(report.verdict))
    banner_border = c("=" * 80, _verdict_color(report.verdict))
    lines.append(banner_border)
    lines.append(f"  {v_colored}")
    lines.append(banner_border)
    lines.append("")

    # 3. Cardinality Counts Table
    counts = report.counts
    lines.append(c("--- Index Cardinality ---", _Colors.BOLD))
    lines.append(f"  Live Vectors       : {counts.live:,}")
    lines.append(f"  Deleted Vectors    : {counts.deleted:,}")
    lines.append(f"  Total Vectors      : {counts.total:,}")
    lines.append(f"  Indexed Vectors    : {counts.indexed:,}")
    lines.append(f"  Degenerate Vectors : {counts.degenerate:,}")
    lines.append(f"  Exact Evaluation   : {counts.exact}")
    lines.append("")

    # 4. Metrics Table
    lines.append(c("--- Audit Metrics ---", _Colors.BOLD))
    # Headers
    h_id = "Metric ID".ljust(22)
    h_state = "State".ljust(13)
    h_val = "Value".rjust(10)
    h_unit = "Unit".ljust(8)
    h_thresh = "Thresholds (warn/fail)".ljust(24)
    h_ev = "Evidence".ljust(8)
    header_line = f"  {h_id} | {h_state} | {h_val} | {h_unit} | {h_thresh} | {h_ev}"
    lines.append(c(header_line, _Colors.BOLD))
    lines.append("  " + "-" * 90)

    for m in report.metrics:
        m_id_str = m.id.ljust(22)
        state_str = m.state.value
        state_formatted = c(state_str.ljust(13), _state_color(m.state))
        val_str = _format_value(m.value).rjust(10)
        unit_str = m.unit.ljust(8)
        thresh_str = _format_thresholds(m).ljust(24)
        ev_str = m.evidence_strength.value.ljust(8)

        line = (
            f"  {m_id_str} | {state_formatted} | {val_str} | "
            f"{unit_str} | {thresh_str} | {ev_str}"
        )
        lines.append(line)

    lines.append("")

    # 5. Metric Explanations & Remediation Details
    detail_metrics = [
        m
        for m in report.metrics
        if m.state in (MetricState.FAIL, MetricState.WARN, MetricState.UNAVAILABLE)
        or m.explanation
        or m.remediation_hint
    ]

    if detail_metrics:
        lines.append(c("--- Metric Details & Diagnostics ---", _Colors.BOLD))
        for m in detail_metrics:
            st_color = _state_color(m.state)
            st_badge = c(f"[{m.state.value}]", st_color)
            lines.append(f"  * {c(m.id, _Colors.BOLD)} {st_badge}:")

            if m.state is MetricState.UNAVAILABLE and m.unavailable_reason:
                lines.append(
                    f"    Reason      : {c(m.unavailable_reason, _Colors.CYAN)}"
                )
            if m.explanation:
                lines.append(f"    Explanation : {m.explanation}")
            if m.remediation_hint:
                lines.append(
                    f"    Remediation : {c(m.remediation_hint, _Colors.YELLOW)}"
                )

        lines.append("")

    # Offending vectors summary (if present in report)
    if report.offending_vector_ids:
        off_ids = ", ".join(str(i) for i in report.offending_vector_ids[:10])
        total_off = len(report.offending_vector_ids)
        more_str = f" (...and {total_off - 10} more)" if total_off > 10 else ""
        lines.append(c("--- Offending Vectors ---", _Colors.BOLD))
        lines.append(f"  Count : {total_off}")
        lines.append(f"  IDs   : [{off_ids}{more_str}]")
        lines.append("")

    # 6. Warnings Section
    if report.warnings:
        lines.append(c("--- Warnings ---", _Colors.BOLD_YELLOW))
        for warn in report.warnings:
            lines.append(f"  ! {c(warn, _Colors.YELLOW)}")
        lines.append("")

    return "\n".join(lines)
