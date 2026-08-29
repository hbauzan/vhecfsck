"""P2-04 nightly-scale ground-truth budget probe.

Absolute wall/RSS numbers are measured in P8-04 and recorded in
``roadmap/release-plan.md`` section 4. Until those cells are filled from a
named reference machine, this module only checks that a reduced-scale blocked
path completes under the working-set math — it does not invent a budget.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import numpy as np
import pytest
from numpy.random import default_rng
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.models import MetricSpace, VectorBatch


@pytest.mark.perf
def test_exact_knn_reduced_scale_completes() -> None:
    """Exercises blocked GT at a CI-safe size; full 1M x 768 waits for P8-04."""
    rng = default_rng(42)
    n, d, q_n, k = 20_000, 64, 32, 10
    corpus = rng.standard_normal((n, d)).astype(np.float32)
    queries = rng.standard_normal((q_n, d)).astype(np.float32)
    ids = np.arange(n, dtype=np.int64)
    batch = VectorBatch(ids=ids, vectors=np.ascontiguousarray(corpus))
    got = exact_knn(
        [batch],
        queries,
        k,
        MetricSpace.L2,
        working_set_mb=32.0,
        n_total=n,
    )
    assert got.truncated is False
    assert got.ids.shape == (q_n, k)
    for qi in range(q_n):
        assert int(got.ids[qi, 0]) >= 0


@pytest.mark.perf
def test_exact_knn_1m_opt_in() -> None:
    """1M x 768 only when explicitly requested; budgets land in P8-04."""
    if os.environ.get("VHECFSCK_PERF_1M") != "1":
        pytest.skip(
            "set VHECFSCK_PERF_1M=1 after P8-04 publishes wall/RSS budgets "
            "in roadmap/release-plan.md section 4"
        )
    rng = default_rng(1)
    n, d, q_n, k = 1_000_000, 768, 200, 10
    queries = rng.standard_normal((q_n, d)).astype(np.float32)

    def corpus_iter() -> Iterator[VectorBatch]:
        chunk = 8192
        for start in range(0, n, chunk):
            stop = min(start + chunk, n)
            vecs = rng.standard_normal((stop - start, d)).astype(np.float32)
            ids = np.arange(start, stop, dtype=np.int64)
            yield VectorBatch(ids=ids, vectors=np.ascontiguousarray(vecs))

    got = exact_knn(
        corpus_iter(),
        queries,
        k,
        MetricSpace.L2,
        working_set_mb=256.0,
        n_total=n,
    )
    assert got.truncated is False
    assert got.ids.shape == (q_n, k)
