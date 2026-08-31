"""Reference performance measurement script for P8-04.

Measures wall-clock time and peak RSS for:
1. Ground truth at 100k x 768 and 1M x 768
2. Hubness at S=20k x 768
3. Deterministic 3D projection at 100k x 768 and 1M x 768
4. Full audit end to end (large synthetic scenario)
5. Scene payload encode / decode
"""

from __future__ import annotations

import resource
import sys
import time
from collections.abc import Iterator
from typing import Any

import numpy as np
from numpy.random import default_rng
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import load_config
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.core.hubness import compute_hubness
from vhecfsck.core.projection import project_to_3d
from vhecfsck.models import MetricSpace, VectorBatch
from vhecfsck.models.scene import LodMetadata, ScenePayload
from vhecfsck.pipeline import run_audit
from vhecfsck.report.scene_codec import decode_scene_binary, encode_scene_binary


def get_peak_rss_mb() -> float:
    """Return peak RSS memory used by this process in MB."""
    ru = resource.getrusage(resource.RUSAGE_SELF)
    if sys.platform == "darwin":
        return ru.ru_maxrss / (1024.0 * 1024.0)
    return ru.ru_maxrss / 1024.0


def measure(name: str, fn) -> tuple[float, float, Any]:
    t0 = time.perf_counter()
    res = fn()
    t1 = time.perf_counter()
    dur = t1 - t0
    rss = get_peak_rss_mb()
    print(f"[{name}] Time: {dur:.4f} s | Peak RSS: {rss:.2f} MB")
    return dur, rss, res


def main() -> None:
    print("=== Reference Performance Measurements ===")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")

    rng = default_rng(42)

    # 1. Ground truth 100k x 768
    def bench_gt_100k():
        n, d, q_n, k = 100_000, 768, 200, 10
        corpus = rng.standard_normal((n, d)).astype(np.float32)
        queries = rng.standard_normal((q_n, d)).astype(np.float32)
        batch = VectorBatch(
            ids=np.arange(n, dtype=np.int64), vectors=np.ascontiguousarray(corpus)
        )
        return exact_knn(
            [batch], queries, k, MetricSpace.L2, working_set_mb=256.0, n_total=n
        )

    t_gt_100k, rss_gt_100k, _ = measure("Ground Truth 100k x 768", bench_gt_100k)

    # 1b. Ground truth 1M x 768 (chunked)
    def bench_gt_1m():
        n, d, q_n, k = 1_000_000, 768, 200, 10
        queries = rng.standard_normal((q_n, d)).astype(np.float32)

        def corpus_iter() -> Iterator[VectorBatch]:
            chunk = 20_000
            for start in range(0, n, chunk):
                stop = min(start + chunk, n)
                vecs = rng.standard_normal((stop - start, d)).astype(np.float32)
                ids = np.arange(start, stop, dtype=np.int64)
                yield VectorBatch(ids=ids, vectors=np.ascontiguousarray(vecs))

        return exact_knn(
            corpus_iter(), queries, k, MetricSpace.L2, working_set_mb=256.0, n_total=n
        )

    t_gt_1m, rss_gt_1m, _ = measure("Ground Truth 1M x 768", bench_gt_1m)

    # 2. Hubness S=20k x 768
    def bench_hubness_20k():
        n, d = 20_000, 768
        vecs = rng.standard_normal((n, d)).astype(np.float32)
        batch = VectorBatch(
            ids=np.arange(n, dtype=np.int64), vectors=np.ascontiguousarray(vecs)
        )
        return compute_hubness(
            corpus_batches=[batch],
            sample_size=20_000,
            k_hub=10,
            metric_space=MetricSpace.L2,
            sample_seed=42,
        )

    t_hub_20k, rss_hub_20k, _ = measure("Hubness S=20k x 768", bench_hubness_20k)

    # 3. Projection 1M x 768
    def bench_proj_1m():
        n, d = 1_000_000, 768
        vecs = rng.standard_normal((n, d)).astype(np.float32)
        return project_to_3d(vecs, seed=42)

    t_proj_1m, rss_proj_1m, _ = measure("Projection 1M x 768", bench_proj_1m)

    # 4. Full audit end to end (large synthetic scenario)
    def bench_audit():
        opened = open_scenario("healthy", size="large")
        try:
            cfg = load_config(cli_overrides={"seed": 42})
            return run_audit(opened.adapter, cfg)
        finally:
            opened.adapter.close()

    t_audit, rss_audit, _r_audit = measure("Full Audit (large scenario)", bench_audit)

    # 5. Scene encode / decode
    n_pts = 100_000
    pos = rng.standard_normal((n_pts, 3)).astype(np.float32)
    cls = rng.integers(0, 4, size=n_pts, dtype=np.uint8)
    p_ids = np.arange(n_pts, dtype=np.int64)
    scene = ScenePayload(
        positions=pos,
        classes=cls,
        ids=p_ids,
        lod=LodMetadata(
            requested_budget=n_pts,
            actual_count=n_pts,
            decimation_method="none",
            complete=True,
            has_tombstones=False,
            total_available=n_pts,
        ),
    )

    def bench_encode():
        return encode_scene_binary(scene)

    t_enc, rss_enc, payload = measure("Scene Encode 100k", bench_encode)

    def bench_decode():
        return decode_scene_binary(payload)

    t_dec, rss_dec, _ = measure("Scene Decode 100k", bench_decode)

    print("\n================ SUMMARY TABLE ================")
    print("| Stage                    | Time (s) | Peak RSS (MB) |")
    print("|--------------------------|----------|---------------|")
    print(f"| Ground Truth (100k x 768)| {t_gt_100k:8.4f} | {rss_gt_100k:13.2f} |")
    print(f"| Ground Truth (1M x 768)  | {t_gt_1m:8.4f} | {rss_gt_1m:13.2f} |")
    print(f"| Hubness (S=20k x 768)    | {t_hub_20k:8.4f} | {rss_hub_20k:13.2f} |")
    print(f"| Projection (1M x 768)    | {t_proj_1m:8.4f} | {rss_proj_1m:13.2f} |")
    print(f"| Full Audit (large)       | {t_audit:8.4f} | {rss_audit:13.2f} |")
    print(f"| Scene Binary Encode 100k | {t_enc:8.4f} | {rss_enc:13.2f} |")
    print(f"| Scene Binary Decode 100k | {t_dec:8.4f} | {rss_dec:13.2f} |")


if __name__ == "__main__":
    main()
