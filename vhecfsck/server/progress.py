"""Stage progress tracking for the live audit feed (P6-02).

Deliberately free of any web framework import so the state machine can be
tested without installing the ``server`` extra. ``routes.py`` is the only place
that knows about WebSockets.

Two properties matter more than the numbers themselves: overall progress never
goes backwards, and no event ever carries a credential or a vector. The second
one is enforced here rather than trusted, because the audit runs against a
production connection and this feed leaves the process.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vhecfsck.logging import redact_secrets

#: Pipeline stages in execution order. ``projection`` is deliberately early:
#: the scene can paint as soon as it resolves, long before hubness finishes.
DEFAULT_STAGES: tuple[str, ...] = (
    "descriptor",
    "counts",
    "projection",
    "canary",
    "hubness",
    "fragmentation",
    "partitions",
    "verdict",
)

#: Pipeline stage names → visualizer stage names. Unknown names are dropped
#: rather than crashing an audit that grew a new stage.
PIPELINE_STAGE_MAP: dict[str, str] = {
    "validate": "descriptor",
    "queries": "counts",
    "ground_truth": "canary",
    "canary": "canary",
    "hubness": "hubness",
    "dfi": "fragmentation",
    "partitions": "partitions",
    "done": "verdict",
}


def map_pipeline_stage(name: str) -> str | None:
    """Translate a ``run_audit`` stage name into a visualizer stage.

    Args:
        name: Stage name emitted by :func:`vhecfsck.pipeline.run_audit`.

    Returns:
        A name in :data:`DEFAULT_STAGES`, or None when the pipeline stage
        has no visualizer counterpart.
    """
    return PIPELINE_STAGE_MAP.get(name)


#: Keys never forwarded to a client, whatever a stage puts in its payload.
_FORBIDDEN_KEYS = frozenset(
    {
        "vector",
        "vectors",
        "query_vector",
        "query_vectors",
        "embedding",
        "embeddings",
        "positions",
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credentials",
        "dsn",
        "connection_string",
    }
)

#: Longest scalar sequence a payload may carry. Anything longer is vector-shaped
#: data rather than a summary and is dropped.
MAX_SEQUENCE_LENGTH = 64


@dataclass(frozen=True)
class ResolvedMetric:
    """A metric that finished while the audit was still running.

    Attributes:
        id: Metric identifier, e.g. ``canary_recall``.
        state: Metric state name, e.g. ``OK`` or ``UNAVAILABLE``.
        value: Scalar value, or None when unavailable.
        unit: Unit of ``value``.
    """

    id: str
    state: str
    value: float | None
    unit: str


@dataclass(frozen=True)
class ProgressEvent:
    """One frame of the progress feed.

    Attributes:
        stage: Stage currently executing.
        stage_index: Zero-based position of ``stage`` in the pipeline.
        stage_count: Total stages.
        stage_fraction: Progress within the current stage, ``[0, 1]``.
        fraction: Overall progress, ``[0, 1]``, never decreasing.
        elapsed_seconds: Time since the tracker started.
        eta_seconds: Estimated time remaining, or None before an estimate is
            meaningful.
        metrics: Every metric resolved so far, in resolution order.
        detail: Sanitised, stage-supplied extras.
        terminal: True on the final event.
    """

    stage: str
    stage_index: int
    stage_count: int
    stage_fraction: float
    fraction: float
    elapsed_seconds: float
    eta_seconds: float | None
    metrics: tuple[ResolvedMetric, ...]
    detail: Mapping[str, Any]
    terminal: bool


def sanitise_detail(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Strip credentials and vector-shaped data from a stage payload.

    Args:
        payload: Arbitrary stage-supplied extras.

    Returns:
        A new mapping safe to send over the wire: forbidden keys removed,
        long numeric sequences dropped, strings passed through the same
        redaction filter as the logs.
    """
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _FORBIDDEN_KEYS:
            continue
        if isinstance(value, str):
            clean[key] = redact_secrets(value)
        elif isinstance(value, bool | int | float) or value is None:
            clean[key] = value
        elif isinstance(value, Mapping):
            clean[key] = sanitise_detail(value)
        elif isinstance(value, Sequence):
            items = list(value)
            if len(items) > MAX_SEQUENCE_LENGTH:
                continue
            if all(isinstance(x, bool | int | float) for x in items):
                clean[key] = items
        # Anything else (arrays, objects, callables) is dropped by omission.
    return clean


@dataclass
class ProgressTracker:
    """Builds a monotonic progress feed for one audit run.

    Attributes:
        stages: Stage names in execution order.
        clock: Monotonic time source; injected so tests need no sleeping.
    """

    stages: tuple[str, ...] = DEFAULT_STAGES
    clock: Callable[[], float] = time.monotonic
    _started_at: float = field(default=0.0, init=False)
    _fraction: float = field(default=0.0, init=False)
    _index: int = field(default=0, init=False)
    _metrics: list[ResolvedMetric] = field(default_factory=list, init=False)
    _terminal: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Anchor the elapsed-time clock and validate the stage list."""
        if not self.stages:
            msg = "at least one stage is required"
            raise ValueError(msg)
        self._started_at = self.clock()

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since the tracker was constructed."""
        return max(0.0, self.clock() - self._started_at)

    def _eta(self) -> float | None:
        # An estimate from almost no progress is noise dressed as information.
        if self._fraction <= 0.02 or self._fraction >= 1.0:
            return None
        elapsed = self.elapsed_seconds
        if elapsed <= 0.0:
            return None
        return (elapsed / self._fraction) - elapsed

    def _emit(
        self,
        *,
        stage_fraction: float,
        detail: Mapping[str, Any] | None,
        terminal: bool,
    ) -> ProgressEvent:
        return ProgressEvent(
            stage=self.stages[self._index],
            stage_index=self._index,
            stage_count=len(self.stages),
            stage_fraction=stage_fraction,
            fraction=self._fraction,
            elapsed_seconds=self.elapsed_seconds,
            eta_seconds=None if terminal else self._eta(),
            metrics=tuple(self._metrics),
            detail=sanitise_detail(detail or {}),
            terminal=terminal,
        )

    def advance(
        self,
        stage: str,
        stage_fraction: float = 0.0,
        *,
        detail: Mapping[str, Any] | None = None,
    ) -> ProgressEvent:
        """Report progress within a stage.

        Args:
            stage: Stage now executing. Must be one of :attr:`stages`.
            stage_fraction: Progress inside that stage, clamped to ``[0, 1]``.
            detail: Optional extras; sanitised before transport.

        Returns:
            The event to broadcast.

        Raises:
            ValueError: If ``stage`` is not a known stage.
        """
        try:
            index = self.stages.index(stage)
        except ValueError:
            known = ", ".join(self.stages)
            msg = f"unknown stage {stage!r}; known stages: {known}"
            raise ValueError(msg) from None

        clamped = min(1.0, max(0.0, float(stage_fraction)))
        self._index = max(self._index, index)
        candidate = (index + clamped) / float(len(self.stages))
        # Monotonic by construction: a stage that reports a stale fraction, or
        # arrives out of order, can never rewind the bar.
        self._fraction = min(1.0, max(self._fraction, candidate))
        return self._emit(stage_fraction=clamped, detail=detail, terminal=False)

    def resolve_metric(
        self,
        metric_id: str,
        *,
        state: str,
        value: float | None,
        unit: str = "",
        detail: Mapping[str, Any] | None = None,
    ) -> ProgressEvent:
        """Publish a metric the moment it resolves.

        Args:
            metric_id: Metric identifier.
            state: Metric state name.
            value: Scalar value, or None when unavailable.
            unit: Unit of ``value``.
            detail: Optional extras; sanitised before transport.

        Returns:
            The event to broadcast, carrying every metric resolved so far.
        """
        self._metrics.append(
            ResolvedMetric(id=metric_id, state=state, value=value, unit=unit)
        )
        return self._emit(stage_fraction=1.0, detail=detail, terminal=False)

    def finish(self, *, detail: Mapping[str, Any] | None = None) -> ProgressEvent:
        """Close the feed.

        Args:
            detail: Optional extras; sanitised before transport.

        Returns:
            The terminal event, at ``fraction == 1.0``.
        """
        self._index = len(self.stages) - 1
        self._fraction = 1.0
        self._terminal = True
        return self._emit(stage_fraction=1.0, detail=detail, terminal=True)

    @property
    def finished(self) -> bool:
        """True once :meth:`finish` has been called."""
        return self._terminal


def event_to_dict(event: ProgressEvent) -> dict[str, Any]:
    """Render an event as the JSON object sent to the browser.

    Args:
        event: Event to serialise.

    Returns:
        A plain dict of JSON-safe values.
    """
    return {
        "stage": event.stage,
        "stage_index": event.stage_index,
        "stage_count": event.stage_count,
        "stage_fraction": round(event.stage_fraction, 6),
        "fraction": round(event.fraction, 6),
        "elapsed_seconds": round(event.elapsed_seconds, 3),
        "eta_seconds": (
            None if event.eta_seconds is None else round(event.eta_seconds, 3)
        ),
        "metrics": [
            {"id": m.id, "state": m.state, "value": m.value, "unit": m.unit}
            for m in event.metrics
        ],
        "detail": dict(event.detail),
        "terminal": event.terminal,
    }
