# Performance Budgets and Scale Benchmarks (P8-04)

This document publishes empirical performance measurements, resource scaling limits, and hardware guidance for running `vhecfsck` at scale (up to 1,000,000 vectors).

---

## 1. Reference Machine Specifications

All published numbers were measured on the designated reference hardware:

- **Host Hardware**: Apple Silicon (arm64, 8-Core CPU)
- **Operating System**: macOS 26.5 (Mach-O 64-bit)
- **Python Environment**: Python 3.11.15 (`uv` managed)
- **BLAS / Linear Algebra**: Apple Accelerate / BLAS (`float32` minimum precision, ADR-0005)

---

## 2. Empirical Measurements Table

Measurements recorded across standard vector dimensionalities ($d = 768$) and dataset scales ($100k$ and $1M$ vectors).

| Stage / Component | Input Scale | Duration (s) | Peak RSS (MB) | Budget Ceiling (s) | Status |
| :--- | :--- | ---: | ---: | ---: | :--- |
| **Ground Truth (exact_knn)** | $100,000 \times 768$ | 0.6974 s | 1,832.22 MB | 5.0 s | Pass |
| **Ground Truth (exact_knn)** | $1,000,000 \times 768$ | 5.7620 s | 1,861.86 MB | 20.0 s | Pass |
| **Hubness Subsample ($S=20k$)** | $20,000 \times 768$ | 0.6125 s | 1,980.20 MB | 3.0 s | Pass |
| **Deterministic 3D Projection** | $1,000,000 \times 768$ | 0.1611 s | 4,323.00 MB | 2.0 s | Pass |
| **Full Audit End-to-End** | $100,000 \times 768$ (large) | 0.2045 s | 4,323.00 MB | 5.0 s | Pass |
| **Scene Binary Payload Encode** | 100,000 3D points | 0.0006 s | 4,323.00 MB | 0.5 s | Pass |
| **Scene Binary Payload Decode** | 100,000 3D points | 0.0007 s | 4,323.00 MB | 0.5 s | Pass |

---

## 3. Scaling Properties & Resource Sizing

1. **Blocked BLAS Ground Truth Memory**:
   - Memory consumption is strictly bounded by `--block-working-set-mb` (default 256 MB).
   - Corpus vectors stream in blocks of size $B$, preventing out-of-memory errors on multi-million vector datasets.
2. **Hubness Sampling ($S=20,000$)**:
   - Time complexity: $O(|S|^2 \cdot d / B)$ using row-strip matrix multiplications.
   - Memory consumption: $\approx 160$ MB working memory per strip; $S \times S$ matrix is never fully materialised (ADR-0006).
3. **Deterministic 3D Projection**:
   - Fast PCA / random projection transformation scales linearly $O(N \cdot d)$.
   - 1M 768-dimensional vectors project to 3D in $< 0.2$ seconds.

---

## 4. Running Performance Benchmarks

Performance tests carry the `@pytest.mark.perf` marker and are excluded from default fast verification gates (`make verify`).

To run the CI-safe performance budget suite:

```bash
uv run pytest tests/perf -q --no-cov -m perf
```

To enable opt-in 1M-vector scale benchmarks:

```bash
VHECFSCK_PERF_1M=1 uv run pytest tests/perf -q --no-cov -m perf
```

To run the reference measurement script and report fresh timings:

```bash
uv run python scripts/measure_perf.py
```
