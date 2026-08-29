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
    "FloatMatrix",
    "IdArray",
    "IndexAdapter",
    "SearchMode",
    "SearchParams",
    "StringIdMapper",
    "SyntheticAdapter",
    "iter_vector_batches",
    "l2_normalize",
]
