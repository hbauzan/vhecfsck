"""Deterministic sampling functions and sub-stream RNG derivation (P2-02).

Provides named sub-streams per purpose (e.g. canary queries, hubness sample),
stable sorted sampling without replacement, and bootstrap resample indices.
"""

from __future__ import annotations

import hashlib

import numpy as np
from numpy.random import Generator, default_rng
from numpy.typing import NDArray


def derive_rng(root_seed: int, purpose: str) -> Generator:
    """Derive a named, deterministic NumPy Generator sub-stream.

    Args:
        root_seed: Root random seed for the audit run.
        purpose: Purpose string for the sub-stream (e.g. 'canary_queries').

    Returns:
        An isolated NumPy Generator instance.
    """
    key = f"{root_seed}:{purpose}".encode()
    digest = hashlib.sha256(key).digest()
    # Extract 32-bit unsigned integer seed from digest
    seed_int = int.from_bytes(digest[:4], byteorder="big", signed=False)
    return default_rng(seed_int)


def sample_without_replacement(
    ids: NDArray[np.int64],
    n: int,
    rng: Generator,
) -> NDArray[np.int64]:
    """Draw a sample of size n without replacement, returning sorted output.

    Args:
        ids: Available candidate IDs.
        n: Requested sample size.
        rng: Derived random number generator.

    Returns:
        NDArray of selected IDs, guaranteed sorted for downstream stability.
    """
    total = len(ids)
    if n >= total:
        sorted_ids: NDArray[np.int64] = np.sort(ids)
        return sorted_ids

    chosen: NDArray[np.int64] = rng.choice(ids, size=n, replace=False)
    sorted_chosen: NDArray[np.int64] = np.sort(chosen)
    return sorted_chosen


def bootstrap_indices(
    n: int,
    resamples: int,
    rng: Generator,
) -> NDArray[np.int64]:
    """Generate bootstrap resample indices of shape (resamples, n).

    Args:
        n: Number of elements in the sample.
        resamples: Number of bootstrap iterations.
        rng: Derived random number generator.

    Returns:
        Array of shape (resamples, n) containing drawn indices in [0, n).
    """
    indices: NDArray[np.int64] = rng.integers(
        0,
        n,
        size=(resamples, n),
        dtype=np.int64,
    )
    return indices
