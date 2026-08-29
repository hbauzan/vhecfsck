"""P2-07: deletion fragmentation index (DFI)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from vhecfsck.core.fragmentation import (
    DFI_FAIL,
    DFI_METRIC_ID,
    DFI_WARN,
    compute_dfi,
    state_from_dfi,
)
from vhecfsck.models import (
    EvidenceStrength,
    IndexCounts,
    MetricSpace,
    MetricState,
)
from vhecfsck.models.metrics import Direction
from vhecfsck.synthetic import (
    apply_churn,
    corpus_state_from_generated,
    generate_corpus,
)


def _counts(
    *,
    live: int,
    deleted: int,
    exact: bool = True,
    total: int | None = None,
) -> IndexCounts:
    tot = total if total is not None else live + deleted
    return IndexCounts(
        live=live,
        deleted=deleted,
        total=tot,
        indexed=tot,
        degenerate=0,
        exact=exact,
        read_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_apply_churn_point_two_yields_dfi_exactly_point_two() -> None:
    """apply_churn(0.2) → DFI exactly 0.2 by construction."""
    gen = generate_corpus(
        500,
        8,
        n_clusters=4,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=1,
        metric_space=MetricSpace.L2,
    )
    state = apply_churn(
        corpus_state_from_generated(gen),
        delete_fraction=0.2,
        skew=0.0,
        seed=2,
    )
    assert state.annotation.dfi == 0.2
    counts = _counts(
        live=int(state.ids.shape[0]) - int(state.annotation.n_deleted),
        deleted=int(state.annotation.n_deleted),
    )
    result = compute_dfi(counts, report_deleted_counts=True)
    assert result.value == 0.2
    assert result.detail["dfi"] == 0.2


def test_missing_deleted_counts_unavailable_never_zero() -> None:
    """CORRECTION 1: report_deleted_counts=False → UNAVAILABLE, never 0.0."""
    result = compute_dfi(
        None,
        report_deleted_counts=False,
    )
    assert result.state is MetricState.UNAVAILABLE
    assert result.value is None
    assert result.unavailable_reason is not None
    assert "deleted" in result.unavailable_reason.lower() or "capability" in (
        result.unavailable_reason.lower()
    )


def test_edge_live_plus_dead_zero_unavailable() -> None:
    """§4.4 case 1."""
    result = compute_dfi(_counts(live=0, deleted=0), report_deleted_counts=True)
    assert result.state is MetricState.UNAVAILABLE
    assert result.value is None


def test_edge_estimated_caps_evidence_medium() -> None:
    """§4.4 case 3: estimated counts → evidence at most medium."""
    result = compute_dfi(
        _counts(live=80, deleted=20, exact=False),
        report_deleted_counts=True,
        estimated=True,
    )
    assert result.state is not MetricState.UNAVAILABLE
    assert result.value == pytest.approx(0.2)
    assert result.evidence_strength is EvidenceStrength.MEDIUM
    assert result.detail["estimated"] is True


def test_edge_proxy_caps_evidence_medium() -> None:
    result = compute_dfi(
        _counts(live=80, deleted=20, exact=True),
        report_deleted_counts=True,
        proxy=True,
    )
    assert result.evidence_strength is EvidenceStrength.MEDIUM
    assert result.detail["proxy"] is True


def test_edge_read_at_timestamp_echoed() -> None:
    """§4.4 case 4: counts read once; timestamp reported."""
    ts = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
    counts = IndexCounts(
        live=90,
        deleted=10,
        total=100,
        indexed=100,
        degenerate=0,
        exact=True,
        read_at=ts,
    )
    result = compute_dfi(counts, report_deleted_counts=True)
    assert result.detail["read_at"] == ts.isoformat()


def test_edge_per_fragment_distribution() -> None:
    """§4.4 case 5: per-fragment breakdown in detail."""
    fragments = (
        {"fragment_id": "a", "live": 50, "deleted": 0},
        {"fragment_id": "b", "live": 40, "deleted": 10},
    )
    result = compute_dfi(
        _counts(live=90, deleted=10),
        report_deleted_counts=True,
        fragments=fragments,
    )
    assert result.value == pytest.approx(0.1)
    dist = result.detail["fragments"]
    assert len(dist) == 2
    assert dist[1]["dfi"] == pytest.approx(0.2)


def test_edge_dead_exceeds_navigable_clamps_to_one() -> None:
    """§4.4 case 6: inconsistent counts → clamp 1.0 + warning."""
    # Negative live makes dead > live + dead.
    result = compute_dfi(
        _counts(live=-5, deleted=20, total=15),
        report_deleted_counts=True,
    )
    assert result.value == 1.0
    assert result.detail["inconsistent_counts"] is True
    assert result.state is MetricState.FAIL


def test_entrypoint_tombstoned_forces_fail() -> None:
    """entrypoint_tombstoned=True → FAIL even at DFI 0.01."""
    result = compute_dfi(
        _counts(live=99, deleted=1),
        report_deleted_counts=True,
        entrypoint_tombstoned=True,
    )
    assert result.value == pytest.approx(0.01)
    assert result.state is MetricState.FAIL
    assert result.detail["entrypoint_tombstoned"] is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.15, MetricState.OK),
        (0.1500001, MetricState.WARN),
        (0.30, MetricState.WARN),
        (0.3000001, MetricState.FAIL),
    ],
)
def test_threshold_boundaries(value: float, expected: MetricState) -> None:
    """Boundaries 0.15 / 0.30 from both sides (higher_is_worse)."""
    assert state_from_dfi(value, warn=DFI_WARN, fail=DFI_FAIL) is expected


def test_exact_healthy_is_ok_high_evidence() -> None:
    result = compute_dfi(_counts(live=100, deleted=0), report_deleted_counts=True)
    assert result.id == DFI_METRIC_ID
    assert result.value == 0.0
    assert result.state is MetricState.OK
    assert result.evidence_strength is EvidenceStrength.HIGH
    assert result.thresholds.direction is Direction.HIGHER_IS_WORSE
