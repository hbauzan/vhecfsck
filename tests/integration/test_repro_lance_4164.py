"""Reproduction test for lancedb/lance#4164 (P5-09).

Scenario:
1. Create dataset with N_0 vectors and build IVF index.
2. Append 10x vectors WITHOUT re-indexing.
3. Observe metric degradation (unindexed rows / recall drop / partition imbalance).
4. Re-index dataset (counterfactual recovery).
5. Assert healthy recovery.
"""

from __future__ import annotations

import tempfile

import numpy as np
import pyarrow as pa
import pytest
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter
from vhecfsck.core.canary import compute_canary_recall
from vhecfsck.core.partitions import compute_partition_cv
from vhecfsck.models import MetricSpace


@pytest.mark.integration
def test_reproduce_lance_4164_unindexed_append_degradation_and_recovery() -> None:
    import lance

    tmp_dir = tempfile.mkdtemp()
    d = 8
    n_initial = 200
    n_append = 1800

    np.random.seed(42)
    vecs_initial = np.random.randn(n_initial, d).astype(np.float32)
    # Unit normalize for clear distance separation
    vecs_initial /= np.linalg.norm(vecs_initial, axis=1, keepdims=True)

    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), d)),
        ]
    )

    tbl_initial = pa.Table.from_arrays(
        [
            pa.array(list(range(n_initial))),
            pa.array(vecs_initial.tolist(), type=pa.list_(pa.float32(), d)),
        ],
        schema=schema,
    )
    lance.write_dataset(tbl_initial, tmp_dir)

    ds = lance.dataset(tmp_dir)
    ds.create_index(
        column="vector",
        index_type="IVF_FLAT",
        metric_type="L2",
        num_partitions=4,
    )

    # 1. Initial audit state
    adapter_initial = LanceDBAdapter(tmp_dir)
    counts_init = adapter_initial.counts()
    assert counts_init.live == n_initial
    assert counts_init.indexed == n_initial
    adapter_initial.close()

    # 2. Append 10x data without re-indexing
    vecs_append = np.random.randn(n_append, d).astype(np.float32)
    vecs_append /= np.linalg.norm(vecs_append, axis=1, keepdims=True)

    tbl_append = pa.Table.from_arrays(
        [
            pa.array(list(range(n_initial, n_initial + n_append))),
            pa.array(vecs_append.tolist(), type=pa.list_(pa.float32(), d)),
        ],
        schema=schema,
    )
    lance.write_dataset(tbl_append, tmp_dir, mode="append")

    # 3. Auditing un-indexed appended dataset
    adapter_unindexed = LanceDBAdapter(tmp_dir)
    counts_unindexed = adapter_unindexed.counts()

    # Assert physical live count is 2000, but indexed count is still 200!
    assert counts_unindexed.live == n_initial + n_append
    assert counts_unindexed.indexed == n_initial
    unindexed_ratio = 1.0 - (counts_unindexed.indexed / counts_unindexed.live)
    assert unindexed_ratio == pytest.approx(0.9, abs=0.01)
    adapter_unindexed.close()

    # 4. Counterfactual: Re-index the grown dataset
    ds_grown = lance.dataset(tmp_dir)
    ds_grown.create_index(
        column="vector",
        index_type="IVF_FLAT",
        metric_type="L2",
        num_partitions=8,
        replace=True,
    )

    # 5. Audit after re-indexing
    all_vecs = np.vstack([vecs_initial, vecs_append])
    queries = vecs_append[:20]
    k = 5
    all_ids = np.arange(n_initial + n_append, dtype=np.int64)

    adapter_reindexed = LanceDBAdapter(tmp_dir)
    counts_reindexed = adapter_reindexed.counts()
    assert counts_reindexed.live == 2000
    assert counts_reindexed.indexed == 2000
    reindexed_unindexed_ratio = 1.0 - (counts_reindexed.indexed / counts_reindexed.live)
    assert reindexed_unindexed_ratio == 0.0

    search_res_healthy = adapter_reindexed.search(queries, k=k, params={"nprobe": 4})
    recall_healthy_res = compute_canary_recall(
        queries=queries,
        returned_ids=search_res_healthy.ids,
        metric_space=MetricSpace.L2,
        k=k,
        search_params={"nprobe": 4},
        corpus_ids=all_ids,
        corpus_vectors=all_vecs,
        self_exclude=False,
        enforce_min_queries=False,
    )

    assert recall_healthy_res.value is not None
    assert recall_healthy_res.value > 0.8, (
        f"Expected healthy recall > 0.8, got {recall_healthy_res.value}"
    )

    parts = adapter_reindexed.partitions()
    assert parts is not None
    cv_healthy = compute_partition_cv(parts)
    assert cv_healthy.value is not None

    adapter_reindexed.close()
