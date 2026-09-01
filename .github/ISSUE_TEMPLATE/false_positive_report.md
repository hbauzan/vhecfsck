---
name: False positive report
about: Report a threshold or metric false positive on a healthy vector index
title: '[FALSE POSITIVE] '
labels: 'false-positive, calibration'
assignees: ''
---

**Corpus & Environment Details**
- Vector dimension $d$: [e.g. 1536]
- Distance metric: [Cosine, L2, Dot]
- Total vectors $N$: [e.g. 100,000]
- Target engine: [LanceDB, Qdrant, pgvector, Synthetic]

**Audit Verdict & Reported Metric**
- Reported Verdict: [WARN / FAIL]
- Metric triggered: [canary_recall, hub_share_top1pct, antihub_fraction, dfi, partition_size_cv]
- Reported Value: [e.g. 0.32]
- Applied Threshold Profile: [e.g. ultra_high (d>1024)]

**Why do you believe this is a false positive?**
Provide empirical ground truth details, recall measurements, or dataset distribution characteristics.

**Sanitized Audit Command & Logs**
```bash
vhecfsck audit ...
```
