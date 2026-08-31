# Read-Only Assurance and Zero Network Egress (`P8-10`)

This document details the read-only assurance model and empirical network egress controls enforced by `vhecfsck`.

## 1. Engine Invariants

- **LanceDB / Lance**: File hashes and modification times (`mtime`) on disk are snapshotted before and after execution. Audit operations use read-only dataset snapshots (`--dataset-version N`) and verify zero bytes written or modified.
- **Qdrant**: Read-only gRPC/HTTP API client sessions. Points, collections, and segment telemetry are introspected without invoking write or compaction endpoints.
- **PostgreSQL / pgvector**: Connections enforce `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` and `default_transaction_read_only=on`. `pg_stat_database` and `pg_stat_user_tables` write counters are verified to remain zero. Minimum-privilege audits run against `SELECT`-only roles.

## 2. Zero Network Egress Control

`vhecfsck` is designed for air-gapped, zero-egress production environments:
- **No Telemetry**: No analytics, usage tracking, or pingbacks.
- **No External Dependencies**: Zero CDN requests, external web fonts, or remote script tags.
- **Empirical Verification**: `tests/integration/test_readonly_all.py` monkeypatches Python's `socket.socket.connect` interface to verify that 0 socket connections are attempted outside the designated local target URI.

## 3. Re-running Verification

Run the full read-only assurance test suite:

```bash
uv run pytest tests/integration/test_readonly_all.py -v
```
