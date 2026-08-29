"""P1-03: synthetic corpus generator."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from vhecfsck.models import MetricSpace
from vhecfsck.synthetic.generator import GeneratedCorpus, generate_corpus


def _row_norms(vectors: np.ndarray) -> list[float]:
    """L2 norms as Python floats (avoid np.all / array_equal under coverage)."""
    return [float(np.sqrt(np.sum(row * row, dtype=np.float32))) for row in vectors]


def test_same_seed_byte_identical_different_seed_differs() -> None:
    a = generate_corpus(
        200,
        16,
        n_clusters=4,
        cluster_std=0.1,
        cluster_size_skew=0.0,
        seed=1337,
        metric_space=MetricSpace.L2,
    )
    b = generate_corpus(
        200,
        16,
        n_clusters=4,
        cluster_std=0.1,
        cluster_size_skew=0.0,
        seed=1337,
        metric_space=MetricSpace.L2,
    )
    c = generate_corpus(
        200,
        16,
        n_clusters=4,
        cluster_std=0.1,
        cluster_size_skew=0.0,
        seed=42,
        metric_space=MetricSpace.L2,
    )
    assert a.vectors.tobytes() == b.vectors.tobytes()
    assert a.ids.tobytes() == b.ids.tobytes()
    assert a.vectors.tobytes() != c.vectors.tobytes()


def test_uniform_skew_near_equal_sizes() -> None:
    corpus = generate_corpus(
        1000,
        8,
        n_clusters=10,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=1,
        metric_space=MetricSpace.L2,
    )
    sizes = [int(np.sum(corpus.cluster_ids == i)) for i in range(10)]
    assert all(abs(s - 100) <= 1 for s in sizes)
    assert sum(sizes) == 1000


def test_high_skew_has_dominant_cluster() -> None:
    corpus = generate_corpus(
        1000,
        8,
        n_clusters=10,
        cluster_std=0.2,
        cluster_size_skew=3.0,
        seed=1,
        metric_space=MetricSpace.L2,
    )
    sizes = sorted(int(np.sum(corpus.cluster_ids == i)) for i in range(10))
    median = sizes[len(sizes) // 2]
    assert sizes[-1] > 3 * median


def test_cosine_norms_unit() -> None:
    corpus = generate_corpus(
        500,
        32,
        n_clusters=5,
        cluster_std=0.15,
        cluster_size_skew=0.5,
        seed=7,
        metric_space=MetricSpace.COSINE,
    )
    assert all(abs(n - 1.0) < 1e-4 for n in _row_norms(corpus.vectors))


def test_shapes_dtype_contiguity_and_spec() -> None:
    corpus = generate_corpus(
        64,
        12,
        n_clusters=3,
        cluster_std=0.1,
        cluster_size_skew=0.0,
        seed=0,
        metric_space=MetricSpace.DOT,
        norm_mean=2.0,
        norm_std=0.0,
    )
    assert isinstance(corpus, GeneratedCorpus)
    assert corpus.ids.shape == (64,)
    assert corpus.vectors.shape == (64, 12)
    assert corpus.cluster_ids.shape == (64,)
    assert corpus.ids.dtype == np.int64
    assert corpus.vectors.dtype == np.float32
    assert corpus.vectors.flags["C_CONTIGUOUS"]
    assert corpus.spec.n == 64
    assert corpus.spec.d == 12
    assert corpus.spec.metric_space is MetricSpace.DOT
    assert corpus.spec.norm_mean == 2.0
    assert all(abs(n - 2.0) < 1e-3 for n in _row_norms(corpus.vectors))


def test_output_float32_and_source_avoids_float64() -> None:
    """Acceptance: float32 path — output dtype + no float64 dtype in generator."""
    corpus = generate_corpus(
        128,
        16,
        n_clusters=4,
        cluster_std=0.1,
        cluster_size_skew=1.0,
        seed=3,
        metric_space=MetricSpace.COSINE,
    )
    assert corpus.vectors.dtype == np.float32
    gen_path = Path(__file__).resolve().parents[2] / "vhecfsck/synthetic/generator.py"
    src = gen_path.read_text(encoding="utf-8")
    assert "float64" not in src
    assert "dtype=np.float32" in src


def test_100k_x_768_under_five_seconds() -> None:
    started = time.perf_counter()
    corpus = generate_corpus(
        100_000,
        768,
        n_clusters=64,
        cluster_std=0.2,
        cluster_size_skew=1.0,
        seed=1337,
        metric_space=MetricSpace.COSINE,
    )
    elapsed = time.perf_counter() - started
    assert corpus.vectors.shape == (100_000, 768)
    assert elapsed < 5.0, f"took {elapsed:.2f}s"
