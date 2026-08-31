# LanceDB Engine Guide

`vhecfsck` provides a native, read-only adapter for auditing **LanceDB** tables and standalone **Lance** datasets.

---

## Quickstart

Audit a local Lance dataset or LanceDB table directory:

```bash
# Audit a Lance dataset directly
vhecfsck audit /path/to/dataset.lance

# Audit with URI scheme
vhecfsck audit lance:///path/to/dataset.lance

# Specify vector column explicitly (if ambiguous)
vhecfsck audit /path/to/dataset.lance --column vector

# Pin exact dataset snapshot version
vhecfsck audit /path/to/dataset.lance --dataset-version 3
```

---

## Engine Capability & Metric Matrix

LanceDB exposes native fragment metadata and index statistics via PyArrow, enabling exact metric accounting without proxy estimates.

| Metric | Support State | Exact / Proxy | Notes |
| :--- | :--- | :--- | :--- |
| **Index Counts** | `OK` | **Exact** | Live, physical, deleted, and indexed counts derived per fragment. |
| **Deletion Fraction (DFI)** | `OK` | **Exact** | Fragment-level deletion accounting without false positives. |
| **Canary Recall** | `OK` | **Exact** | Native k-NN search vs blocked ground truth (`float16` upcast to `float32`). |
| **IVF Partition CV** | `OK` | **Exact** | Introspects cell row counts directly from index statistics. |
| **Graph Stats** | `UNAVAILABLE` | N/A | LanceDB does not use graph-based indexes (uses IVF / IVF-PQ). |

---

## Snapshot Version Pinning (`--dataset-version N`)

Lance datasets are append-only and versioned via commit logs (`_versions/*.manifest`).

By default or via `--dataset-version N`, `vhecfsck` opens a fixed snapshot version. This structurally eliminates mid-audit mutation issues (`snapshot_inconsistent` warning), guaranteeing exact reproducibility across runs.

```bash
vhecfsck audit lance:///path/to/dataset.lance?dataset_version=2
```

---

## Version Compatibility Matrix

`vhecfsck` pins and tests specific version ranges for `lance` (`pylance`) and `lancedb`:

| Package | Tested Version Range | Extra Specification |
| :--- | :--- | :--- |
| `pylance` (`lance`) | `>=0.11.0, <12.0.0` | `vhecfsck[lancedb]` |
| `lancedb` | `>=0.37.1, <1.0.0` | `vhecfsck[lancedb]` |

If runtime versions fall outside the tested window, `vhecfsck` emits a single warning without aborting the audit.

---

## Read-Only Invariant & Security Verification

`vhecfsck` accesses Lance datasets strictly read-only via PyArrow scanners and native index readers.

- **Filesystem Hash Invariance**: Automated test harness (`tests/integration/test_readonly_lancedb.py`) verifies zero file additions, deletions, or modification diffs (SHA-256 + mtime) during audits.
- **`chmod -R a-w` Verified**: Audits run cleanly against directories mounted read-only without write permission.
- **AST Guard Enforced**: Prohibits mutator calls (`.add()`, `.delete()`, `.drop()`) in `vhecfsck/adapters/`.
