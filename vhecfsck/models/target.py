"""Target and capability descriptors for an audited vector index.

Leaf types: stdlib only. Callers must pass an already-redacted ``location``
(via ``vhecfsck.logging.redact_secrets``) so reports stay safe to share.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MetricSpace(Enum):
    """Distance / similarity space read from the target index."""

    COSINE = "COSINE"
    L2 = "L2"
    DOT = "DOT"


class IndexKind(Enum):
    """Coarse index topology; ``UNKNOWN`` when the engine cannot say."""

    FLAT = "FLAT"
    IVF = "IVF"
    IVF_PQ = "IVF_PQ"
    HNSW = "HNSW"
    HNSW_PQ = "HNSW_PQ"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Capabilities:
    """Optional reads an adapter claims.

    Defaults are all ``False``: forgetting to opt in degrades a metric to
    ``UNAVAILABLE`` rather than inventing a number.
    """

    enumerate_vectors: bool = False
    random_access_by_id: bool = False
    report_deleted_counts: bool = False
    deleted_counts_exact: bool = False
    report_partitions: bool = False
    partition_live_counts: bool = False
    report_graph_stats: bool = False
    search_params_settable: bool = False
    filtered_search: bool = False


@dataclass(frozen=True)
class TargetDescriptor:
    """Identity of the index under audit (location must already be redacted)."""

    engine: str
    engine_version: str
    index_kind: IndexKind
    index_name: str
    location: str
    dimension: int
    metric_space: MetricSpace
