"""Shared pytest fixtures for determinism across the suite."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest


@pytest.fixture
def rng() -> np.random.Generator:
    """Seeded Generator — never use the global numpy RNG in tests."""
    return np.random.default_rng(0)


@pytest.fixture(autouse=True)
def deterministic_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin hash seed and single-threaded BLAS for reproducible numerics.

    Multi-threaded BLAS reduction order is not deterministic; pinning threads
    avoids flaky floating-point comparisons once metrics land.
    """
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "1")
    monkeypatch.setenv("MKL_NUM_THREADS", "1")
    monkeypatch.setenv("NUMEXPR_NUM_THREADS", "1")
    yield
