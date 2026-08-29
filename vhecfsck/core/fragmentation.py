"""Deletion fragmentation index (DFI) — ``02-metrics-spec.md`` §4 (P2-07).

Pure computation over ``IndexCounts`` (+ optional fragment breakdown).
Engine-specific count derivation stays in adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vhecfsck.models import (
    EvidenceStrength,
    IndexCounts,
    MetricResult,
    MetricState,
    ThresholdSpec,
)
from vhecfsck.models.metrics import Direction

DFI_METRIC_ID = "dfi"
DFI_WARN = 0.15
DFI_FAIL = 0.30


def state_from_dfi(
    value: float,
    *,
    warn: float = DFI_WARN,
    fail: float = DFI_FAIL,
) -> MetricState:
    """Map DFI to OK/WARN/FAIL (``higher_is_worse``, §4 thresholds)."""
    if value > fail:
        return MetricState.FAIL
    if value > warn:
        return MetricState.WARN
    return MetricState.OK


def _unavailable(
    reason: str,
    *,
    sampling: Mapping[str, Any],
    detail: Mapping[str, Any],
    evidence: EvidenceStrength,
    warn: float,
    fail: float,
) -> MetricResult:
    return MetricResult(
        id=DFI_METRIC_ID,
        state=MetricState.UNAVAILABLE,
        value=None,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=warn, fail=fail, direction=Direction.HIGHER_IS_WORSE
        ),
        sampling=dict(sampling),
        detail=dict(detail),
        evidence_strength=evidence,
        unavailable_reason=reason,
    )


def compute_dfi(
    counts: IndexCounts | None,
    *,
    report_deleted_counts: bool = True,
    estimated: bool = False,
    proxy: bool = False,
    fragments: Sequence[Mapping[str, Any]] | None = None,
    entrypoint_tombstoned: bool | None = None,
    warn: float = DFI_WARN,
    fail: float = DFI_FAIL,
) -> MetricResult:
    """Compute DFI = dead / (live + dead) (``02-metrics-spec.md`` §4.1).

    Parameters
    ----------
    report_deleted_counts:
        Adapter capability. When False → ``UNAVAILABLE`` (CORRECTION 1), never
        a fabricated ``0.0``.
    estimated / proxy:
        Cap ``evidence_strength`` at ``medium`` (§4.2 / §4.4).
    fragments:
        Optional per-fragment ``{fragment_id, live, deleted}`` rows; each gets
        its own ``dfi`` in ``detail.fragments``.
    entrypoint_tombstoned:
        When True, escalate state to ``FAIL`` regardless of the ratio (§4.3).
    """
    sampling: dict[str, Any] = {
        "report_deleted_counts": report_deleted_counts,
        "estimated": estimated,
        "proxy": proxy,
    }
    base_detail: dict[str, Any] = {
        "dfi": None,
        "estimated": estimated,
        "proxy": proxy,
        "inconsistent_counts": False,
        "entrypoint_tombstoned": entrypoint_tombstoned,
        "fragments": [],
        "read_at": None,
    }

    if not report_deleted_counts:
        return _unavailable(
            "capability report_deleted_counts missing — cannot compute DFI",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )
    if counts is None:
        return _unavailable(
            "IndexCounts unavailable — cannot compute DFI",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )

    live = int(counts.live)
    dead = int(counts.deleted)
    navigable = live + dead
    base_detail["read_at"] = counts.read_at.isoformat()
    sampling["live"] = live
    sampling["deleted"] = dead
    sampling["total"] = int(counts.total)
    sampling["exact"] = bool(counts.exact)

    if navigable == 0:
        return _unavailable(
            "live + dead == 0 (empty index)",
            sampling=sampling,
            detail=base_detail,
            evidence=EvidenceStrength.LOW,
            warn=warn,
            fail=fail,
        )

    inconsistent = dead > navigable
    dfi = 1.0 if inconsistent else dead / float(navigable)

    frag_out: list[dict[str, Any]] = []
    if fragments is not None:
        for row in fragments:
            f_live = int(row["live"])
            f_dead = int(row["deleted"])
            f_nav = f_live + f_dead
            f_dfi = 1.0 if f_nav <= 0 or f_dead > f_nav else f_dead / float(f_nav)
            frag_out.append(
                {
                    "fragment_id": row.get("fragment_id"),
                    "live": f_live,
                    "deleted": f_dead,
                    "dfi": f_dfi,
                }
            )

    # Evidence: exact non-proxy → high; estimates/proxies capped at medium.
    is_exact = bool(counts.exact) and not estimated and not proxy
    evidence = EvidenceStrength.HIGH if is_exact else EvidenceStrength.MEDIUM

    detail: dict[str, Any] = {
        "dfi": dfi,
        "estimated": estimated or (not counts.exact),
        "proxy": proxy,
        "inconsistent_counts": inconsistent,
        "entrypoint_tombstoned": entrypoint_tombstoned,
        "fragments": frag_out,
        "read_at": counts.read_at.isoformat(),
    }

    state = state_from_dfi(dfi, warn=warn, fail=fail)
    if entrypoint_tombstoned is True:
        state = MetricState.FAIL

    return MetricResult(
        id=DFI_METRIC_ID,
        state=state,
        value=dfi,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=warn, fail=fail, direction=Direction.HIGHER_IS_WORSE
        ),
        sampling=sampling,
        detail=detail,
        evidence_strength=evidence,
        explanation="Deletion fragmentation index: dead / (live + dead).",
        remediation_hint=(
            "compact or rebuild to clear tombstones"
            if state is not MetricState.OK
            else ""
        ),
    )
