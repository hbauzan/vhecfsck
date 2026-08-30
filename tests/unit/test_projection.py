"""Unit tests for deterministic 3D PCA projection (P4-01)."""

from __future__ import annotations

import numpy as np
from vhecfsck.core.projection import fit_projection_basis, project_to_3d


def test_projection_determinism() -> None:
    """Same seed and input produce bit-identical positions and variance ratios."""
    rng = np.random.default_rng(42)
    vectors = rng.standard_normal((100, 32), dtype=np.float32)

    res1 = project_to_3d([vectors], seed=42)
    res2 = project_to_3d([vectors], seed=42)

    assert np.array_equal(res1.positions, res2.positions)
    assert res1.scale == res2.scale
    assert res1.explained_variance_ratio == res2.explained_variance_ratio
    assert res1.explained_variance_sum == res2.explained_variance_sum
    assert np.array_equal(res1.fitted_components, res2.fitted_components)


def test_projection_svd_flip_sign_convention() -> None:
    """Negating input maintains component sign convention."""
    rng = np.random.default_rng(123)
    vectors = rng.standard_normal((50, 16), dtype=np.float32)

    basis1 = fit_projection_basis([vectors])
    basis2 = fit_projection_basis([-vectors])

    for comp in basis1.components:
        max_idx = np.argmax(np.abs(comp))
        assert comp[max_idx] >= 0.0

    for comp in basis2.components:
        max_idx = np.argmax(np.abs(comp))
        assert comp[max_idx] >= 0.0


def test_projection_explained_variance_properties() -> None:
    """Variance ratios are monotonically decreasing and sum to <= 1.0."""
    rng = np.random.default_rng(99)
    vectors = rng.standard_normal((200, 64), dtype=np.float32)

    res = project_to_3d([vectors], n_components=3)

    ratios = res.explained_variance_ratio
    assert len(ratios) == 3
    assert ratios[0] >= ratios[1] >= ratios[2]
    assert 0.0 <= res.explained_variance_sum <= 1.0 + 1e-6
    assert abs(res.explained_variance_sum - sum(ratios)) < 1e-6


def test_projection_normalization_cube() -> None:
    """Output positions fit inside display cube [-1, 1]^3."""
    rng = np.random.default_rng(7)
    vectors = rng.standard_normal((80, 128), dtype=np.float32)

    res = project_to_3d([vectors], n_components=3)

    assert res.positions.shape == (80, 3)
    assert res.positions.dtype == np.float32
    assert np.all(res.positions >= -1.0 - 1e-5)
    assert np.all(res.positions <= 1.0 + 1e-5)


def test_projection_streaming_matches_chunked() -> None:
    """Streaming vectors in multiple blocks matches single chunk fit within 1e-4."""
    rng = np.random.default_rng(101)
    data = rng.standard_normal((300, 24), dtype=np.float32)

    block1 = data[:100]
    block2 = data[100:200]
    block3 = data[200:]

    res_single = project_to_3d([data], n_components=3)
    res_streaming = project_to_3d([block1, block2, block3], n_components=3)

    assert np.allclose(res_single.positions, res_streaming.positions, atol=1e-4)
    assert abs(res_single.scale - res_streaming.scale) < 1e-4
    for r1, r2 in zip(
        res_single.explained_variance_ratio,
        res_streaming.explained_variance_ratio,
        strict=True,
    ):
        assert abs(r1 - r2) < 1e-4


def test_projection_degenerate_fewer_than_3_vectors() -> None:
    """Handles inputs with < 3 vectors cleanly without crashing."""
    vectors_2 = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)

    res = project_to_3d([vectors_2], n_components=3)

    assert res.positions.shape == (2, 3)
    assert len(res.explained_variance_ratio) == 3
    assert np.all(np.isfinite(res.positions))


def test_projection_degenerate_identical_vectors() -> None:
    """Handles zero-variance identical vectors without division by zero or NaN."""
    vectors_identical = np.tile(np.array([1.0, -2.0, 3.0], dtype=np.float32), (20, 1))

    res = project_to_3d([vectors_identical], n_components=3)

    assert res.positions.shape == (20, 3)
    assert np.all(np.isfinite(res.positions))
    assert res.explained_variance_sum == 0.0


def test_projection_fitted_basis_reuse() -> None:
    """Live and tombstoned vectors projected using the same fitted basis."""
    rng = np.random.default_rng(55)
    live = rng.standard_normal((100, 16), dtype=np.float32)
    tombstones = rng.standard_normal((20, 16), dtype=np.float32)

    basis = fit_projection_basis([live])
    res_live = basis.transform(live)
    res_tomb = basis.transform(tombstones)

    assert res_live.shape == (100, 3)
    assert res_tomb.shape == (20, 3)
    assert np.all(np.isfinite(res_live))
    assert np.all(np.isfinite(res_tomb))
