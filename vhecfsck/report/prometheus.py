"""Prometheus textfile collector exporter for audit reports (P3-06).

Provides Prometheus metrics output for audit reports. Labels are low cardinality
and redacted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from vhecfsck.models.metrics import MetricState, Verdict
from vhecfsck.models.report import Report

_VERDICT_NUM: dict[Verdict, int] = {
    Verdict.OK: 0,
    Verdict.WARN: 1,
    Verdict.FAIL: 2,
    Verdict.INCONCLUSIVE: 3,
}

_STATE_NUM: dict[MetricState, int] = {
    MetricState.OK: 0,
    MetricState.WARN: 1,
    MetricState.FAIL: 2,
    MetricState.UNAVAILABLE: 3,
    MetricState.DISABLED: 4,
}

_METRIC_GAUGE_NAMES: dict[str, str] = {
    "canary_recall": "vhecfsck_canary_recall",
    "dfi": "vhecfsck_dfi_ratio",
    "hub_share_top1pct": "vhecfsck_hub_share_top1pct",
    "antihub_fraction": "vhecfsck_antihub_fraction",
    "partition_size_cv": "vhecfsck_partition_size_cv",
}

_METRIC_GAUGE_HELP: dict[str, str] = {
    "canary_recall": "Canary recall accuracy score (0.0 to 1.0).",
    "dfi": "Deleted vector fragmentation index ratio.",
    "hub_share_top1pct": "Fraction of k-NN slots occupied by top 1% hubs.",
    "antihub_fraction": "Fraction of vectors never appearing in k-NN returns.",
    "partition_size_cv": "Coefficient of variation across index partition sizes.",
}


def _parse_timestamp(iso_str: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.timestamp()
    except Exception:
        return datetime.now(tz=UTC).timestamp()


def _format_labels(labels: dict[str, Any]) -> str:
    parts = []
    for k, v in sorted(labels.items()):
        val_str = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        parts.append(f'{k}="{val_str}"')
    return "{" + ",".join(parts) + "}"


def render_prometheus(report: Report) -> str:
    """Render an Audit Report into Prometheus textfile-collector format."""
    lines: list[str] = []

    target = report.target
    common_labels = {
        "engine": target.engine,
        "index": target.index_name,
        "metric_space": target.metric_space.value,
        "target": target.location,
    }
    lbl_str = _format_labels(common_labels)

    # 1. Process Status / Audit Up
    lines.append("# HELP vhecfsck_up Process readiness status (1 = audit complete).")
    lines.append("# TYPE vhecfsck_up gauge")
    lines.append(f"vhecfsck_up{lbl_str} 1")

    # 2. Overall Audit Verdict
    v_val = _VERDICT_NUM.get(report.verdict, 3)
    lines.append(
        "# HELP vhecfsck_audit_verdict Audit verdict code "
        "(0=OK, 1=WARN, 2=FAIL, 3=INCONCLUSIVE)."
    )
    lines.append("# TYPE vhecfsck_audit_verdict gauge")
    lines.append(f"vhecfsck_audit_verdict{lbl_str} {v_val}")

    # 3. Timings & Timestamps
    lines.append(
        "# HELP vhecfsck_audit_duration_seconds Total wall-clock time for run."
    )
    lines.append("# TYPE vhecfsck_audit_duration_seconds gauge")
    lines.append(
        f"vhecfsck_audit_duration_seconds{lbl_str} {report.run.duration_seconds:.6f}"
    )

    ts = _parse_timestamp(report.run.started_at)
    lines.append(
        "# HELP vhecfsck_audit_timestamp_seconds Unix timestamp when audit started."
    )
    lines.append("# TYPE vhecfsck_audit_timestamp_seconds gauge")
    lines.append(f"vhecfsck_audit_timestamp_seconds{lbl_str} {ts:.3f}")

    # 4. Cardinality Counts
    lines.append(
        "# HELP vhecfsck_vectors_live Count of active live vectors in target index."
    )
    lines.append("# TYPE vhecfsck_vectors_live gauge")
    lines.append(f"vhecfsck_vectors_live{lbl_str} {report.counts.live}")

    lines.append(
        "# HELP vhecfsck_vectors_deleted Count of tombstoned vectors in target index."
    )
    lines.append("# TYPE vhecfsck_vectors_deleted gauge")
    lines.append(f"vhecfsck_vectors_deleted{lbl_str} {report.counts.deleted}")

    # 5. Individual Metric Gauges
    for m in report.metrics:
        gname = _METRIC_GAUGE_NAMES.get(m.id)
        if gname:
            help_msg = _METRIC_GAUGE_HELP.get(m.id, f"Metric value for {m.id}.")
            lines.append(f"# HELP {gname} {help_msg}")
            lines.append(f"# TYPE {gname} gauge")
            if m.state != MetricState.UNAVAILABLE and m.value is not None:
                lines.append(f"{gname}{lbl_str} {m.value:.6f}")

        # Metric State Gauge
        lines.append(
            "# HELP vhecfsck_metric_state Metric state code "
            "(0=OK, 1=WARN, 2=FAIL, 3=UNAVAILABLE, 4=DISABLED)."
        )
        lines.append("# TYPE vhecfsck_metric_state gauge")
        m_lbls = dict(common_labels)
        m_lbls["metric"] = m.id
        s_val = _STATE_NUM.get(m.state, 3)
        lines.append(f"vhecfsck_metric_state{_format_labels(m_lbls)} {s_val}")

        # Metric Unavailable Flag
        lines.append(
            "# HELP vhecfsck_metric_unavailable Flag whether metric was unavailable "
            "(1=true, 0=false)."
        )
        lines.append("# TYPE vhecfsck_metric_unavailable gauge")
        unavail_val = 1 if m.state == MetricState.UNAVAILABLE else 0
        lines.append(
            f"vhecfsck_metric_unavailable{_format_labels(m_lbls)} {unavail_val}"
        )

    return "\n".join(lines) + "\n"
