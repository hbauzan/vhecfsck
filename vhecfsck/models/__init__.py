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
    EvidenceStrength,
    MetricResult,
    MetricState,
    ThresholdSpec,
)
from vhecfsck.models.target import (
    Capabilities,
    IndexKind,
    MetricSpace,
    TargetDescriptor,
)

__all__ = [
    "Capabilities",
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
]
