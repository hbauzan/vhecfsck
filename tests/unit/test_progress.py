"""Unit tests for the live audit progress feed (P6-02)."""

from __future__ import annotations

import pytest
from vhecfsck.server.progress import (
    DEFAULT_STAGES,
    MAX_SEQUENCE_LENGTH,
    PIPELINE_STAGE_MAP,
    ProgressTracker,
    event_to_dict,
    map_pipeline_stage,
    sanitise_detail,
)


class _Clock:
    """Deterministic monotonic clock so tests never sleep."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


def _tracker(clock: _Clock | None = None) -> ProgressTracker:
    return ProgressTracker(clock=clock or _Clock())


# --- monotonic progress ------------------------------------------------------


def test_progress_advances_monotonically_and_reaches_a_terminal_state() -> None:
    tracker = _tracker()

    fractions = [tracker.advance(stage, 1.0).fraction for stage in DEFAULT_STAGES]
    final = tracker.finish()

    assert fractions == sorted(fractions)
    assert final.terminal is True
    assert final.fraction == 1.0
    assert tracker.finished is True


def test_a_stale_stage_report_cannot_rewind_the_bar() -> None:
    """Out-of-order events are a fact of concurrent pipelines, not a bug."""
    tracker = _tracker()
    tracker.advance("hubness", 0.5)

    rewound = tracker.advance("counts", 0.1)

    assert rewound.fraction >= 0.5 / len(DEFAULT_STAGES)
    assert rewound.fraction == pytest.approx(
        (DEFAULT_STAGES.index("hubness") + 0.5) / len(DEFAULT_STAGES)
    )


def test_stage_fraction_is_clamped() -> None:
    tracker = _tracker()

    assert tracker.advance("counts", 5.0).stage_fraction == 1.0
    assert tracker.advance("counts", -3.0).stage_fraction == 0.0


def test_overall_fraction_never_exceeds_one() -> None:
    tracker = _tracker()

    event = tracker.advance(DEFAULT_STAGES[-1], 1.0)

    assert event.fraction <= 1.0


def test_unknown_stage_is_rejected_and_names_the_known_ones() -> None:
    tracker = _tracker()

    with pytest.raises(ValueError, match="hubness"):
        tracker.advance("teleport")


def test_an_empty_stage_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one stage"):
        ProgressTracker(stages=())


# --- timing ------------------------------------------------------------------


def test_elapsed_time_tracks_the_clock() -> None:
    clock = _Clock()
    tracker = _tracker(clock)
    clock.tick(12.5)

    assert tracker.advance("counts", 0.5).elapsed_seconds == pytest.approx(12.5)


def test_no_eta_is_offered_before_progress_is_meaningful() -> None:
    clock = _Clock()
    tracker = _tracker(clock)
    clock.tick(1.0)

    assert tracker.advance(DEFAULT_STAGES[0], 0.0).eta_seconds is None


def test_eta_extrapolates_from_elapsed_time() -> None:
    clock = _Clock()
    tracker = _tracker(clock)
    clock.tick(10.0)

    # Half way through the pipeline after ten seconds implies ten more.
    event = tracker.advance(DEFAULT_STAGES[len(DEFAULT_STAGES) // 2], 0.0)

    assert event.fraction == pytest.approx(0.5)
    assert event.eta_seconds == pytest.approx(10.0)


def test_the_terminal_event_offers_no_eta() -> None:
    clock = _Clock()
    tracker = _tracker(clock)
    clock.tick(3.0)
    tracker.advance("hubness", 0.5)

    assert tracker.finish().eta_seconds is None


# --- incremental metrics -----------------------------------------------------


def test_metrics_appear_incrementally_rather_than_all_at_once() -> None:
    """A six-minute audit with a spinner feels broken; stages feel fast."""
    tracker = _tracker()

    first = tracker.resolve_metric(
        "canary_recall", state="OK", value=0.93, unit="ratio"
    )
    second = tracker.resolve_metric("hub_share", state="WARN", value=0.11, unit="ratio")

    assert [m.id for m in first.metrics] == ["canary_recall"]
    assert [m.id for m in second.metrics] == ["canary_recall", "hub_share"]
    assert second.metrics[1].state == "WARN"


def test_an_unavailable_metric_carries_a_null_value() -> None:
    tracker = _tracker()

    event = tracker.resolve_metric("partition_cv", state="UNAVAILABLE", value=None)

    assert event.metrics[0].value is None


def test_resolved_metrics_survive_to_the_terminal_event() -> None:
    tracker = _tracker()
    tracker.resolve_metric("canary_recall", state="OK", value=1.0)

    assert len(tracker.finish().metrics) == 1


# --- sanitisation ------------------------------------------------------------


def test_events_carry_no_credentials() -> None:
    clean = sanitise_detail(
        {
            "password": "hunter2",
            "api_key": "sk-live-abc",
            "token": "t0ken",
            "dsn": "postgres://u:p@host/db",
            "stage_note": "connected",
        }
    )

    assert set(clean) == {"stage_note"}


def test_credential_bearing_strings_are_redacted_not_forwarded() -> None:
    clean = sanitise_detail({"note": "connecting to postgres://user:pw@host/db"})

    assert "pw" not in clean["note"]


def test_events_carry_no_vector_data() -> None:
    clean = sanitise_detail(
        {
            "vectors": [[0.1, 0.2], [0.3, 0.4]],
            "embedding": [0.5, 0.6],
            "positions": [1.0, 2.0, 3.0],
            "n_live": 1_000,
        }
    )

    assert set(clean) == {"n_live"}


def test_long_numeric_sequences_are_dropped_as_vector_shaped() -> None:
    clean = sanitise_detail(
        {
            "short": [1.0] * MAX_SEQUENCE_LENGTH,
            "long": [1.0] * (MAX_SEQUENCE_LENGTH + 1),
        }
    )

    assert set(clean) == {"short"}


def test_nested_payloads_are_sanitised_too() -> None:
    clean = sanitise_detail({"outer": {"api_key": "abc", "count": 3}})

    assert clean["outer"] == {"count": 3}


def test_non_scalar_sequences_are_dropped() -> None:
    clean = sanitise_detail({"objects": [{"a": 1}], "ok": 2})

    assert set(clean) == {"ok"}


def test_tracker_sanitises_detail_it_is_handed() -> None:
    tracker = _tracker()

    event = tracker.advance("counts", 0.5, detail={"token": "secret", "rows": 5})

    assert dict(event.detail) == {"rows": 5}


# --- serialisation -----------------------------------------------------------


def test_event_serialises_to_json_safe_primitives() -> None:
    clock = _Clock()
    tracker = _tracker(clock)
    clock.tick(2.0)
    tracker.resolve_metric("canary_recall", state="OK", value=0.9, unit="ratio")

    payload = event_to_dict(tracker.advance("hubness", 0.25, detail={"rows": 7}))

    assert payload["stage"] == "hubness"
    assert payload["metrics"] == [
        {"id": "canary_recall", "state": "OK", "value": 0.9, "unit": "ratio"}
    ]
    assert payload["detail"] == {"rows": 7}
    assert payload["terminal"] is False
    assert isinstance(payload["fraction"], float)


def test_scene_can_paint_once_projection_resolves() -> None:
    """Projection precedes hubness, so the cloud appears before the metrics."""
    assert DEFAULT_STAGES.index("projection") < DEFAULT_STAGES.index("hubness")


def test_pipeline_stages_map_onto_visualizer_stages() -> None:
    assert map_pipeline_stage("dfi") == "fragmentation"
    assert map_pipeline_stage("done") == "verdict"
    assert map_pipeline_stage("validate") == "descriptor"
    assert map_pipeline_stage("teleport") is None
    assert set(PIPELINE_STAGE_MAP.values()) <= set(DEFAULT_STAGES)
