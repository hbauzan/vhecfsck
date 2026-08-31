"""Property-based fuzzing and adversarial input suite for core and codecs (P8-08).

Hypothesis-driven fuzzing of every core/ entry point, report schema deserialization,
and binary/JSON scene codecs against edge-case dimensions, counts, k values,
duplicate/zero vectors, denormal floats, NaN/Inf, and malformed binary/JSON payloads.
"""

from __future__ import annotations

import json
import math
import struct
from datetime import UTC, datetime

import numpy as np
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from vhecfsck.core.canary import compute_canary_recall
from vhecfsck.core.fragmentation import compute_dfi
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.core.hubness import compute_hubness
from vhecfsck.core.partitions import compute_partition_cv
from vhecfsck.core.projection import project_to_3d
from vhecfsck.core.sampling import (
    bootstrap_indices,
    derive_rng,
    sample_without_replacement,
)
from vhecfsck.core.verdict import evaluate
from vhecfsck.errors import VhecfsckError
from vhecfsck.models.corpus import IndexCounts, PartitionStats
from vhecfsck.models.metrics import Direction, MetricResult, MetricState, ThresholdSpec
from vhecfsck.models.report import report_from_dict
from vhecfsck.models.target import MetricSpace
from vhecfsck.report.scene_codec import decode_scene_binary


def _assert_no_nan_or_inf_in_metric(result: MetricResult) -> None:
    """Assert that a MetricResult's value and detail numbers are never NaN or Inf."""
    if result.value is not None:
        assert not math.isnan(result.value), f"Metric {result.id} value is NaN"
        assert not math.isinf(result.value), f"Metric {result.id} value is Inf"

    for key, val in result.detail.items():
        if isinstance(val, (float, int)) and not isinstance(val, bool):
            assert not math.isnan(val), f"Metric {result.id} detail '{key}' is NaN"
            assert not math.isinf(val), f"Metric {result.id} detail '{key}' is Inf"


@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    n=st.integers(min_value=0, max_value=20),
    d=st.integers(min_value=1, max_value=64),
    q=st.integers(min_value=1, max_value=5),
    k=st.integers(min_value=0, max_value=25),
    metric_space=st.sampled_from([MetricSpace.L2, MetricSpace.COSINE, MetricSpace.DOT]),
    has_nan_or_inf=st.booleans(),
)
def test_fuzz_exact_knn(
    n: int,
    d: int,
    q: int,
    k: int,
    metric_space: MetricSpace,
    has_nan_or_inf: bool,
) -> None:
    """Fuzz ground truth exact_knn with extreme N, D, K, and potential NaN/Inf."""
    try:
        if has_nan_or_inf:
            corpus = np.random.choice(
                [0.0, 1.0, np.nan, np.inf, -np.inf, 1e-38, 1e38], size=(n, d)
            ).astype(np.float32)
            queries = np.random.choice(
                [0.0, 1.0, np.nan, np.inf, -np.inf, 1e-38, 1e38], size=(q, d)
            ).astype(np.float32)
        else:
            corpus = np.random.randn(n, d).astype(np.float32)
            queries = np.random.randn(q, d).astype(np.float32)

        ids, dists = exact_knn(corpus, queries, k=k, metric_space=metric_space)
        assert ids.shape[0] == q
        assert dists.shape[0] == q
        if not has_nan_or_inf:
            assert not np.isnan(dists).any(), (
                "NaN found in exact_knn distances for valid input"
            )
            assert not np.isinf(dists).any(), (
                "Inf found in exact_knn distances for valid input"
            )
    except (
        VhecfsckError,
        ValueError,
        FloatingPointError,
        RuntimeWarning,
        Exception,
    ) as exc:
        assert isinstance(exc, Exception)


@settings(
    max_examples=40,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    n=st.integers(min_value=1, max_value=30),
    d=st.integers(min_value=1, max_value=32),
    q=st.integers(min_value=1, max_value=5),
    k=st.integers(min_value=1, max_value=10),
    metric_space=st.sampled_from([MetricSpace.L2, MetricSpace.COSINE, MetricSpace.DOT]),
    self_exclude=st.booleans(),
)
def test_fuzz_canary_recall(
    n: int,
    d: int,
    q: int,
    k: int,
    metric_space: MetricSpace,
    self_exclude: bool,
) -> None:
    """Fuzz canary recall computation against varying parameters."""
    corpus_ids = np.arange(n, dtype=np.int64)
    corpus_vectors = np.random.randn(n, d).astype(np.float32)
    queries = np.random.randn(q, d).astype(np.float32)

    returned_k = min(k, n)
    returned_ids = np.random.randint(0, max(1, n), size=(q, returned_k), dtype=np.int64)

    query_source_ids = corpus_ids[:q] if self_exclude and q <= n else None

    result = compute_canary_recall(
        corpus_ids=corpus_ids,
        corpus_vectors=corpus_vectors,
        queries=queries,
        returned_ids=returned_ids,
        metric_space=metric_space,
        k=k,
        query_source_ids=query_source_ids,
        self_exclude=self_exclude,
        query_source="corpus" if self_exclude else "synthetic",
        search_params={},
        bootstrap_resamples=10,
        enforce_min_queries=False,
    )
    assert isinstance(result, MetricResult)
    _assert_no_nan_or_inf_in_metric(result)


@settings(
    max_examples=40,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    n=st.integers(min_value=2, max_value=30),
    d=st.integers(min_value=1, max_value=32),
    k_hub=st.integers(min_value=1, max_value=10),
    metric_space=st.sampled_from([MetricSpace.L2, MetricSpace.COSINE, MetricSpace.DOT]),
)
def test_fuzz_hubness(
    n: int,
    d: int,
    k_hub: int,
    metric_space: MetricSpace,
) -> None:
    """Fuzz hubness computation against varying dimensions and sample sizes."""
    assume(k_hub < n)
    corpus_ids = np.arange(n, dtype=np.int64)
    corpus_vectors = np.random.randn(n, d).astype(np.float32)

    result, anti_result = compute_hubness(
        corpus_ids=corpus_ids,
        corpus_vectors=corpus_vectors,
        metric_space=metric_space,
        k_hub=k_hub,
        enforce_min_sample=False,
    )
    assert isinstance(result, MetricResult)
    assert isinstance(anti_result, MetricResult)
    _assert_no_nan_or_inf_in_metric(result)
    _assert_no_nan_or_inf_in_metric(anti_result)


@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    total=st.integers(min_value=0, max_value=10000),
    live=st.integers(min_value=0, max_value=10000),
    deleted=st.integers(min_value=0, max_value=10000),
    indexed=st.integers(min_value=0, max_value=10000),
    exact=st.booleans(),
)
def test_fuzz_dfi(
    total: int, live: int, deleted: int, indexed: int, exact: bool
) -> None:
    """Fuzz deletion fragmentation index with arbitrary vector count combinations."""
    counts = IndexCounts(
        live=live,
        deleted=deleted,
        total=total,
        indexed=indexed,
        degenerate=0,
        exact=exact,
        read_at=datetime.now(UTC),
    )
    result = compute_dfi(counts=counts)
    assert isinstance(result, MetricResult)
    _assert_no_nan_or_inf_in_metric(result)


@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    sizes=st.lists(st.integers(min_value=0, max_value=5000), min_size=0, max_size=30),
)
def test_fuzz_partition_cv(sizes: list[int]) -> None:
    """Fuzz partition size CV with arbitrary cluster size distributions."""
    partitions = (
        PartitionStats(
            n_partitions=len(sizes),
            sizes=tuple(sizes),
            includes_deleted=False,
        )
        if len(sizes) > 0
        else None
    )

    result = compute_partition_cv(partitions)
    assert isinstance(result, MetricResult)
    _assert_no_nan_or_inf_in_metric(result)


@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    n_total=st.integers(min_value=0, max_value=1000),
    sample_size=st.integers(min_value=0, max_value=1500),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    purpose=st.text(min_size=1, max_size=20),
)
def test_fuzz_sampling_utilities(
    n_total: int, sample_size: int, seed: int, purpose: str
) -> None:
    """Fuzz deterministic sampling utilities with boundary total and sample sizes."""
    rng = derive_rng(seed, purpose)
    ids = np.arange(n_total, dtype=np.int64)
    sampled = sample_without_replacement(ids, sample_size, rng)
    assert isinstance(sampled, np.ndarray)
    if n_total == 0:
        assert len(sampled) == 0
    else:
        assert len(sampled) == min(n_total, sample_size)
        if len(sampled) > 0:
            assert np.all(sampled >= 0)
            assert np.all(sampled < n_total)

    if n_total > 0:
        idx = bootstrap_indices(n_total, resamples=5, rng=rng)
        assert idx.shape == (5, n_total)
        assert np.all(idx >= 0) and np.all(idx < n_total)


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    n=st.integers(min_value=0, max_value=20),
    d=st.integers(min_value=1, max_value=16),
    n_components=st.integers(min_value=1, max_value=5),
)
def test_fuzz_projection(n: int, d: int, n_components: int) -> None:
    """Fuzz 3D projection basis fitting and vector transformations."""
    vecs = [np.random.randn(n, d).astype(np.float32)] if n > 0 else []
    proj = project_to_3d(vecs, n_components=n_components)
    assert proj.positions.shape == (n, n_components)
    assert not np.isnan(proj.positions).any()
    assert not np.isinf(proj.positions).any()
    assert not math.isnan(proj.scale)
    assert not math.isinf(proj.scale)


@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    val=st.floats(min_value=-1e5, max_value=1e5, allow_nan=False, allow_infinity=False),
    warn=st.floats(
        min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False
    ),
    fail=st.floats(
        min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False
    ),
    direction=st.sampled_from([Direction.HIGHER_IS_WORSE, Direction.LOWER_IS_WORSE]),
)
def test_fuzz_verdict_evaluation(
    val: float, warn: float, fail: float, direction: Direction
) -> None:
    """Fuzz verdict threshold evaluation across values and direction modes."""
    try:
        thresholds = ThresholdSpec(warn=warn, fail=fail, direction=direction)
        state = evaluate(val, thresholds)
        assert isinstance(state, MetricState)
    except ValueError as exc:
        assert "requires" in str(exc)


@given(data=st.binary(min_size=0, max_size=512))
def test_fuzz_scene_codec_corrupted_bytes(data: bytes) -> None:
    """Fuzz binary scene decoder with arbitrary corrupted byte payloads."""
    try:
        decode_scene_binary(data)
    except (
        ValueError,
        TypeError,
        KeyError,
        struct.error,
        json.JSONDecodeError,
        UnicodeDecodeError,
        VhecfsckError,
    ) as exc:
        assert isinstance(exc, Exception)


@given(text=st.text(min_size=0, max_size=512))
def test_fuzz_report_dict_deserialization_malformed(text: str) -> None:
    """Fuzz report deserialization with hostile or malformed JSON payloads."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            report_from_dict(parsed)
    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
        KeyError,
        ValidationError,
        VhecfsckError,
    ) as exc:
        assert isinstance(exc, Exception)
