# CI Integration Recipes

This document provides copy-pasteable configuration recipes for integrating `vhecfsck` into CI/CD pipelines, orchestrators (Airflow/Dagster), and monitoring automation.

---

## Exit Code Handling Strategy

`vhecfsck` uses a strict exit code taxonomy:

| Code | Status | Pipeline Action | Description |
| :---: | :--- | :--- | :--- |
| **`0`** | **`OK`** | Pass build | All metrics pass healthy thresholds. |
| **`1`** | **`WARN`** | Non-blocking annotation | Warning threshold breached; annotate job without failing pipeline unless `--fail-on-warn` is set. |
| **`2`** | **`FAIL`** | Fail build | Critical quality degradation; block deployment. |
| **`3`** | **`INCONCLUSIVE`** | Configuration issue | Audit cannot complete due to unsupported engine capability or sample size constraint. |
| **`4`** | **`USAGE`** | Infrastructure failure | CLI argument error, target connection loss (`TargetConnectionError`), or memory budget exceeded (`ResourceError`). |
| **`70`** | **`INTERNAL`** | Engine error | Unhandled process exception. |

---

## 1. GitHub Actions Composite Action

Use the built-in composite action in your GitHub Actions workflows:

```yaml
name: Audit Vector Index

on:
  push:
    branches: [ main ]
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Audit Vector Index
        uses: ./.github/actions/vhecfsck
        with:
          target: 'postgres://user:pass@localhost:5432/vectors'
          options: '--only canary_recall,dfi'
          fail-on-warn: 'false'
          export-summary: 'true'
```

### GitHub Step Summary Example

To render audit reports directly into the GitHub Actions step summary markdown:

```bash
uvx vhecfsck audit "postgres://user:pass@localhost:5432/db" --format json > report.json
echo "## Vector Index Audit Summary" >> $GITHUB_STEP_SUMMARY
uvx vhecfsck export report.json --format markdown >> $GITHUB_STEP_SUMMARY
```

---

## 2. GitLab CI

Reference example: [`examples/gitlab-ci.yml`](https://github.com/hbauzan/vhecfsck/blob/main/examples/gitlab-ci.yml)

```yaml
vector_audit:
  stage: test
  image: python:3.11-slim
  script:
    - pip install uv
    - |
      uvx vhecfsck audit "$VECTOR_DB_URI" --format text > audit.txt 2>&1 || EXIT_CODE=$?
      cat audit.txt
      if [ ${EXIT_CODE:-0} -eq 2 ]; then exit 2; fi
  artifacts:
    when: always
    paths:
      - audit.txt
```

---

## 3. Kubernetes CronJob (Prometheus Textfile Collector)

Reference example: [`examples/k8s-cronjob.yaml`](https://github.com/hbauzan/vhecfsck/blob/main/examples/k8s-cronjob.yaml)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: vhecfsck-audit
spec:
  schedule: "0 */4 * * *"
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
              uvx vhecfsck audit "$VECTOR_DB_URI" --format prometheus > /node_exporter/textfile/vhecfsck.prom.tmp
              mv /node_exporter/textfile/vhecfsck.prom.tmp /node_exporter/textfile/vhecfsck.prom
            volumeMounts:
            - name: textfile-collector
              mountPath: /node_exporter/textfile
          restartPolicy: OnFailure
          volumes:
          - name: textfile-collector
            hostPath:
              path: /var/lib/node_exporter/textfile_collector
```

---

## 4. Crontab

Reference example: [`examples/crontab.example`](https://github.com/hbauzan/vhecfsck/blob/main/examples/crontab.example)

```bash
0 */6 * * * uvx vhecfsck audit postgres://vuser:vpass@127.0.0.1:5432/vectordb --format prometheus > /var/lib/node_exporter/textfile_collector/vhecfsck.prom.tmp && mv /var/lib/node_exporter/textfile_collector/vhecfsck.prom.tmp /var/lib/node_exporter/textfile_collector/vhecfsck.prom
```

---

## 5. Apache Airflow DAG

Reference example: [`examples/airflow_dag.py`](https://github.com/hbauzan/vhecfsck/blob/main/examples/airflow_dag.py)

```python
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG("vhecfsck_audit", schedule_interval="0 4 * * *") as dag:
    audit_task = BashOperator(
        task_id="run_vhecfsck_audit",
        bash_command='uvx vhecfsck audit "$VECTOR_DB_URI" --format text',
    )
```

---

## 6. Dagster Job

Reference example: [`examples/dagster_job.py`](https://github.com/hbauzan/vhecfsck/blob/main/examples/dagster_job.py)

```python
from dagster import job, op
import subprocess


@op
def run_audit():
    res = subprocess.run(
        ["uvx", "vhecfsck", "audit", "synthetic://healthy", "--format", "json"],
        capture_output=True,
        text=True,
    )
    if res.returncode == 2:
        raise ValueError("Audit failed threshold check")


@job
def audit_job():
    run_audit()
```

---

## 7. Prometheus Alerting Rules & Companion Staleness Alert

An audit that stopped executing looks identical to an index that is passing! Always configure companion staleness alerts on `vhecfsck_metric_unavailable`:

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
          summary: "Canary recall fell below failure threshold (< 0.70)"

      - alert: VectorIndexTombstoneFragmentation
        expr: vhecfsck_dfi > 0.30
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Deletion fragmentation index high (> 0.30)"

      - alert: VectorIndexAuditStale
        expr: vhecfsck_metric_unavailable{metric="canary_recall"} == 1 or absent(vhecfsck_canary_recall)
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Vector index audit metric is unavailable or halted"
```
