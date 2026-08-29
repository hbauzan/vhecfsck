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

__all__ = [
    "DENIED_WRITE_NAMES",
    "FloatMatrix",
    "IdArray",
    "IndexAdapter",
    "SearchParams",
    "StringIdMapper",
    "iter_vector_batches",
    "l2_normalize",
]
