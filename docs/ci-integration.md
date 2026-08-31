# CI Integration Recipes

This document provides copy-pasteable configuration recipes for integrating `vhecfsck` into CI/CD pipelines and monitoring automation.

---

## Exit Code Handling Strategy

`vhecfsck` uses a strict exit code taxonomy:

| Code | Status | Pipeline Action |
| :---: | :--- | :--- |
| **`0`** | **`OK`** | Pass build. |
| **`1`** | **`WARN`** | Pass build with job warning annotation. |
| **`2`** | **`FAIL`** | Fail build and block deployment. |
| **`3`** | **`INCONCLUSIVE`** | Fail pipeline configuration step (needs resolution). |
| **`4`** | **`USAGE`** | Fail build (invalid flags, target down, or OOM). |
| **`70`** | **`INTERNAL`** | Fail build (unexpected exception). |

---

## 1. GitHub Actions

```yaml
name: Vector Index Audit

on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Run vhecfsck audit
        run: |
          uvx vhecfsck audit postgres://user:pass@localhost:5432/db \
            --only canary_recall,dfi \
            --format text
```

---

## 2. GitLab CI

```yaml
vector_audit:
  stage: test
  image: python:3.11-slim
  script:
    - pip install uv
    - uvx vhecfsck audit qdrant+http://qdrant:6333/my_collection --format text
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
```

---

## 3. Kubernetes CronJob (Prometheus Textfile Exporter)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: vhecfsck-audit
spec:
  schedule: "0 */6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: auditor
            image: python:3.11-slim
            command:
            - /bin/sh
            - -c
            - |
              pip install uv
              uvx vhecfsck audit lancedb:///data/indexes/my_dataset --format prometheus > /node_exporter/textfile/vhecfsck.prom
            volumeMounts:
            - name: textfile-dir
              mountPath: /node_exporter/textfile
          restartPolicy: OnFailure
          volumes:
          - name: textfile-dir
            hostPath:
              path: /var/lib/node_exporter/textfile_collector
```

---

## 4. Prometheus Alerting Rules

```yaml
groups:
  - name: vhecfsck_alerts
    rules:
      - alert: VectorIndexRecallDecay
        expr: vhecfsck_canary_recall < 0.70
        for: 15m
        labels:
          severity: critical
        annotations:
          summary: "Vector index canary recall fell below failure threshold (< 0.70)"

      - alert: VectorIndexTombstoneFragmentation
        expr: vhecfsck_dfi > 0.30
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Vector index deletion fragmentation index high (> 0.30)"

      - alert: VectorIndexAuditStale
        expr: vhecfsck_metric_unavailable == 1
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Vector index audit metric is unavailable or halted"
```
