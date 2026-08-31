# Scenario Reproduction: lancedb/lance#4164

## Overview

In LanceDB / Lance datasets, appending new vectors (`mode="append"`) adds them to new or existing data fragments without automatically updating or re-clustering pre-existing vector indexes (`IVF_FLAT` / `IVF_PQ`).

As a result, while `counts().live` grows, `counts().indexed` remains frozen at the initial size ($N_0$), creating a significant ratio of unindexed vectors that are excluded or degraded during vector search.

Upstream Issue: [lancedb/lance#4164](https://github.com/lancedb/lance/issues/4164)

---

## Measured Pathology Evidence

The automated test `tests/integration/test_repro_lance_4164.py` reproduces and verifies this behavior deterministically:

| Audit Stage | Live Rows | Indexed Rows | Unindexed Ratio | Vector Index State |
| :--- | :--- | :--- | :--- | :--- |
| **1. Initial Indexing** | 200 | 200 | 0.00 (0%) | Healthy (`IVF_FLAT`) |
| **2. Appended (+10x data)** | 2,000 | 200 | 0.90 (90%) | Pathological (Unindexed rows) |
| **3. Counterfactual Re-index** | 2,000 | 2,000 | 0.00 (0%) | Restored Healthy (`IVF_FLAT`) |

---

## Detection in `vhecfsck`

`vhecfsck` audits LanceDB datasets read-only and flags this condition by checking:
1. `counts().live` vs `counts().indexed`: Discrepancy signals unindexed appended rows.
2. `IndexCounts(exact=True)`: Accurately isolates unindexed rows per fragment.
3. Canary Recall & Partition CV: Introspects search recall and cell distribution.

---

## Remediation

To resolve this condition, rebuild or optimize the dataset index:
```python
import lance

ds = lance.dataset("/path/to/dataset.lance")
ds.create_index(
    column="vector",
    index_type="IVF_FLAT",
    metric_type="L2",
    replace=True,
)
```
After re-indexing, `vhecfsck audit` confirms `counts().indexed == counts().live` with zero unindexed gap.
