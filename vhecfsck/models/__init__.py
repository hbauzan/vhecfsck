"""Shared domain types and report models.

Typed strictly: mypy --strict and ruff ANN+D. Leaf package — no I/O, no
metric logic, imports only stdlib and numpy (see roadmap/01-architecture.md §4).
"""

from vhecfsck.models.corpus import (
    GraphStats,
    IndexCounts,
    PartitionStats,
    SearchResult,
    VectorBatch,
)
from vhecfsck.models.metrics import (
    Direction,
    EvidenceStrength,
    MetricResult,
    MetricState,
    ThresholdSpec,
    Verdict,
    metric_result_from_dict,
    metric_result_to_dict,
)
from vhecfsck.models.target import (
    Capabilities,
    IndexKind,
    MetricSpace,
    TargetDescriptor,
)

__all__ = [
    "Capabilities",
    "Direction",
    "EvidenceStrength",
    "GraphStats",
    "IndexCounts",
    "IndexKind",
    "MetricResult",
    "MetricSpace",
    "MetricState",
    "PartitionStats",
    "SearchResult",
    "TargetDescriptor",
    "ThresholdSpec",
    "VectorBatch",
    "Verdict",
    "metric_result_from_dict",
    "metric_result_to_dict",
]
