"""Shared pytest fixtures and process configuration for determinism across the suite."""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import signal
import sys
from collections.abc import Iterator

import numpy as np
import pytest


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Set process-level defaults for signal handlers and numeric thread limits."""
    # Cap thread pools for BLAS/OpenMP before C extensions initialize
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ.setdefault(key, "1")

    def _handle_signal(signum: int, _frame: object) -> None:
        msg = f"\n[pytest] Received signal {signum}; terminating test process...\n"
        sys.stderr.write(msg)
        sys.stderr.flush()
        sys.exit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        with contextlib.suppress(AttributeError, ValueError):
            signal.signal(sig, _handle_signal)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # noqa: ARG001
    """Ensure clean process termination when test session completes.

    Prevents lingering non-daemon background threads or unclosed IPC pipes from
    hanging during Python interpreter finalization.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with contextlib.suppress(Exception):
        for child in multiprocessing.active_children():
            child.terminate()


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: pytest.Config) -> None:
    """Force OS-level process exit as the absolute last unconfigure hook.

    By using trylast=True, allows pytest-cov and other plugins to finish writing
    their report artifacts (coverage.xml, XML dumps) before terminating the process,
    bypassing Py_Finalize C-extension spin loops in select_poll_poll.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    code = getattr(config, "exitstatus", 0)
    os._exit(code)


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
    monkeypatch.setenv("VECLIB_MAXIMUM_THREADS", "1")
    monkeypatch.setenv("NUMEXPR_NUM_THREADS", "1")
    yield
