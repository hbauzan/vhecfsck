"""Deterministic 3D incremental PCA projection module.

Projects high-dimensional vector embeddings into display coordinates.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


@dataclass(frozen=True)
class ProjectionResult:
    """Result of projecting high-dimensional vectors into normalized 3D space.

    Attributes:
        positions: Matrix of shape (N, n_components) in [-1, 1]^3.
        scale: Scale factor applied during normalization.
        explained_variance_ratio: Tuple of explained variance ratios per component.
        explained_variance_sum: Sum of explained variance ratios.
        fitted_components: Projection basis matrix of shape (n_components, d).
    """

    positions: NDArray[np.float32]
    scale: float
    explained_variance_ratio: tuple[float, ...]
    explained_variance_sum: float
    fitted_components: NDArray[np.float32]


@dataclass(frozen=True)
class ProjectionBasis:
    """Fitted PCA basis capable of projecting arbitrary vector arrays.

    Attributes:
        mean: Mean vector of shape (d,).
        components: Basis vectors of shape (n_components, d).
        explained_variance: Eigenvalues corresponding to components.
        explained_variance_ratio: Variance ratio per component.
        explained_variance_sum: Sum of variance ratios.
        scale: Normalization scale factor derived from training data.
    """

    mean: NDArray[np.float64]
    components: NDArray[np.float64]
    explained_variance: NDArray[np.float64]
    explained_variance_ratio: tuple[float, ...]
    explained_variance_sum: float
    scale: float

    def transform(
        self,
        vectors: NDArray[np.float32] | NDArray[np.float64],
    ) -> NDArray[np.float32]:
        """Project vectors using the fitted basis into normalized 3D coordinates.

        Args:
            vectors: Array of shape (M, d) to project.

        Returns:
            Array of shape (M, n_components) normalized to display cube.
        """
        if vectors.size == 0:
            return np.empty((0, self.components.shape[0]), dtype=np.float32)

        centered = vectors.astype(np.float64) - self.mean
        projected = np.dot(centered, self.components.T)
        normalized = projected / self.scale if self.scale > 1e-12 else projected
        clipped = np.clip(normalized, -1.0, 1.0).astype(np.float32)

        return cast("NDArray[np.float32]", clipped)


def fit_projection_basis(
    vectors_iter: Iterable[NDArray[np.float32] | NDArray[np.float64]],
    *,
    n_components: int = 3,
    sample_size: int | None = None,
) -> ProjectionBasis:
    """Fit a deterministic PCA basis over streamed vector blocks using svd_flip.

    Args:
        vectors_iter: Iterable emitting blocks of vectors (float32 or float64).
        n_components: Target number of projection dimensions (default: 3).
        sample_size: Optional maximum total vectors to sample for fitting.

    Returns:
        Fitted ProjectionBasis instance.
    """
    total_count = 0
    dim = 0
    sum_vec: NDArray[np.float64] | None = None
    outer_sum: NDArray[np.float64] | None = None

    for block in vectors_iter:
        if block.size == 0:
            continue
        if dim == 0:
            dim = int(block.shape[1])
            sum_vec = np.zeros(dim, dtype=np.float64)
            outer_sum = np.zeros((dim, dim), dtype=np.float64)

        if sum_vec is None or outer_sum is None:
            continue

        block_f64 = block.astype(np.float64)
        if sample_size is not None and total_count + block_f64.shape[0] > sample_size:
            take = sample_size - total_count
            if take <= 0:
                break
            block_f64 = block_f64[:take]

        n_b = block_f64.shape[0]
        total_count += n_b
        sum_vec += np.sum(block_f64, axis=0)
        outer_sum += np.dot(block_f64.T, block_f64)

        if sample_size is not None and total_count >= sample_size:
            break

    if total_count == 0 or dim == 0 or sum_vec is None or outer_sum is None:
        eye_mat = np.eye(n_components, max(n_components, dim), dtype=np.float64)
        components = eye_mat[:n_components, :dim]
        return ProjectionBasis(
            mean=np.zeros(dim, dtype=np.float64),
            components=components,
            explained_variance=np.zeros(n_components, dtype=np.float64),
            explained_variance_ratio=tuple(0.0 for _ in range(n_components)),
            explained_variance_sum=0.0,
            scale=1.0,
        )

    mean = sum_vec / float(total_count)

    denom = float(max(1, total_count - 1))
    cov = (outer_sum - float(total_count) * np.outer(mean, mean)) / denom
    cov = (cov + cov.T) / 2.0

    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    total_var = float(np.sum(np.maximum(eigenvalues, 0.0)))
    top_evals = np.maximum(eigenvalues[:n_components], 0.0)

    if total_var > 1e-12:
        ratios_list = [float(v / total_var) for v in top_evals]
    else:
        ratios_list = [0.0] * n_components

    if dim < n_components:
        padded_components = np.zeros((n_components, dim), dtype=np.float64)
        padded_components[:dim, :] = eigenvectors.T[:dim, :]
        for i in range(dim, n_components):
            padded_components[i, i % dim] = 1.0
        components = padded_components
        top_evals = np.pad(top_evals, (0, n_components - dim))
        ratios_list.extend([0.0] * (n_components - len(ratios_list)))
    else:
        components = eigenvectors.T[:n_components, :]

    for i in range(components.shape[0]):
        max_idx = int(np.argmax(np.abs(components[i])))
        if components[i, max_idx] < 0.0:
            components[i] = -components[i]

    scale = float(np.sqrt(np.max(top_evals) * 3.0)) if np.max(top_evals) > 0 else 1.0
    if scale < 1e-6:
        scale = 1.0

    explained_var_ratio = tuple(ratios_list[:n_components])
    var_sum = float(sum(explained_var_ratio))

    return ProjectionBasis(
        mean=mean,
        components=components,
        explained_variance=top_evals[:n_components],
        explained_variance_ratio=explained_var_ratio,
        explained_variance_sum=var_sum,
        scale=scale,
    )


def project_to_3d(
    vectors_blocks: Iterable[NDArray[np.float32] | NDArray[np.float64]],
    *,
    n_components: int = 3,
    seed: int | None = None,
    sample_size: int | None = None,
) -> ProjectionResult:
    """Project high-dimensional vectors to normalized 3D display coordinates.

    Args:
        vectors_blocks: Iterable emitting blocks of vectors.
        n_components: Target dimensions (default: 3).
        seed: Optional RNG seed (used if sampling is active).
        sample_size: Optional maximum vectors to fit basis.

    Returns:
        ProjectionResult containing positions normalized in [-1, 1]^3, scale factor,
        and explained variance metrics.
    """
    _ = seed
    blocks = [b for b in vectors_blocks if b.size > 0]
    if not blocks:
        empty_pos = np.empty((0, n_components), dtype=np.float32)
        empty_comp = np.zeros((n_components, 0), dtype=np.float32)
        return ProjectionResult(
            positions=empty_pos,
            scale=1.0,
            explained_variance_ratio=tuple(0.0 for _ in range(n_components)),
            explained_variance_sum=0.0,
            fitted_components=empty_comp,
        )

    basis = fit_projection_basis(
        blocks,
        n_components=n_components,
        sample_size=sample_size,
    )

    if len(blocks) > 1:
        full_matrix: NDArray[np.float32] | NDArray[np.float64] = cast(
            "NDArray[np.float32] | NDArray[np.float64]",
            np.vstack(blocks),
        )
    else:
        full_matrix = blocks[0]

    projected = basis.transform(full_matrix)

    max_val = float(np.max(np.abs(projected)))
    if max_val > 1e-6:
        final_positions = (projected / max_val).astype(np.float32)
        final_scale = basis.scale * max_val
    else:
        final_positions = projected.astype(np.float32)
        final_scale = basis.scale

    comp_f32 = basis.components.astype(np.float32)
    return ProjectionResult(
        positions=final_positions,
        scale=final_scale,
        explained_variance_ratio=basis.explained_variance_ratio,
        explained_variance_sum=basis.explained_variance_sum,
        fitted_components=comp_f32,
    )
