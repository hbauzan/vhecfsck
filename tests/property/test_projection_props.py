"""Property-based invariant tests for 3D PCA projection (P4-01)."""

from __future__ import annotations

import numpy as np
from vhecfsck.core.projection import fit_projection_basis, project_to_3d


def test_projection_property_invariants_across_dimensions() -> None:
    """Validate invariants across random dimensions and sample sizes."""
    seeds = [1, 42, 99, 555]
    dims = [3, 8, 32, 128]
    counts = [5, 50, 150]

    for seed in seeds:
        for d in dims:
            for n in counts:
                rng = np.random.default_rng(seed)
                vectors = rng.standard_normal((n, d), dtype=np.float32)

                res = project_to_3d([vectors], n_components=3)

                # Property 1: Output shape and type
                assert res.positions.shape == (n, 3)
                assert res.positions.dtype == np.float32

                # Property 2: Display cube boundary
                assert np.all(res.positions >= -1.0 - 1e-5)
                assert np.all(res.positions <= 1.0 + 1e-5)

                # Property 3: Variance ratio ordering and sum
                ratios = res.explained_variance_ratio
                assert len(ratios) == 3
                assert ratios[0] >= ratios[1] - 1e-6
                assert ratios[1] >= ratios[2] - 1e-6
                assert 0.0 <= res.explained_variance_sum <= 1.0 + 1e-5

                # Property 4: Fitted basis dimensions
                assert res.fitted_components.shape == (3, d)

                # Property 5: Component sign determinism (svd_flip)
                basis = fit_projection_basis([vectors], n_components=3)
                for comp in basis.components:
                    max_idx = np.argmax(np.abs(comp))
                    assert comp[max_idx] >= 0.0
