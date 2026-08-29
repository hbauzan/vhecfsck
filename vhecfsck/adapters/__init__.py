"""Engine adapters behind IndexAdapter — typed strictly (mypy --strict)."""

from vhecfsck.adapters.base import (
    DENIED_WRITE_NAMES,
    FloatMatrix,
    IdArray,
    IndexAdapter,
    SearchParams,
    StringIdMapper,
    iter_vector_batches,
    l2_normalize,
)
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter
from vhecfsck.adapters.postgres_adapter import PostgresAdapter
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter
from vhecfsck.adapters.registry import (
    SUPPORTED_SCHEMES,
    open_target,
    register,
    registered_schemes,
    resolve_class,
)
from vhecfsck.adapters.synthetic_adapter import (
    RECALL_COLLAPSE_DELETE_FRACTION,
    RECALL_COLLAPSE_EF_BUDGET,
    RECALL_COLLAPSE_NPROBE,
    SearchMode,
    SyntheticAdapter,
)

__all__ = [
    "DENIED_WRITE_NAMES",
    "RECALL_COLLAPSE_DELETE_FRACTION",
    "RECALL_COLLAPSE_EF_BUDGET",
    "RECALL_COLLAPSE_NPROBE",
    "SUPPORTED_SCHEMES",
    "FloatMatrix",
    "IdArray",
    "IndexAdapter",
    "LanceDBAdapter",
    "PostgresAdapter",
    "QdrantAdapter",
    "SearchMode",
    "SearchParams",
    "StringIdMapper",
    "SyntheticAdapter",
    "iter_vector_batches",
    "l2_normalize",
    "open_target",
    "register",
    "registered_schemes",
    "resolve_class",
]
