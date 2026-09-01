"""Dagster job recipe for running vhecfsck vector index audits.

P9-03 Integration Recipe.
"""

from __future__ import annotations

import subprocess

from dagster import Field, OpExecutionContext, Out, String, job, op


@op(
    config_schema={"target_uri": Field(String, default_value="synthetic://healthy")},
    out=Out(str),
)
def run_vhecfsck_audit_op(context: OpExecutionContext) -> str:
    """Execute vhecfsck audit CLI process and return JSON output payload."""
    target_uri = context.op_config["target_uri"]
    context.log.info(f"Starting vhecfsck audit against {target_uri}")

    res = subprocess.run(
        ["uvx", "vhecfsck", "audit", target_uri, "--format", "json"],
        capture_output=True,
        text=True,
    )

    exit_code = res.returncode
    context.log.info(f"vhecfsck exit code: {exit_code}")

    if exit_code == 0:
        context.log.info("Audit verdict: OK")
    elif exit_code == 1:
        context.log.warning("Audit verdict: WARN threshold breached")
    elif exit_code == 2:
        raise ValueError(f"vhecfsck audit FAILED with threshold breach: {res.stdout}")
    elif exit_code == 3:
        context.log.warning(f"vhecfsck audit INCONCLUSIVE: {res.stderr}")
    else:
        raise RuntimeError(f"vhecfsck execution error (code {exit_code}): {res.stderr}")

    return res.stdout


@job
def vhecfsck_audit_job() -> None:
    """Dagster job executing vector index audit operator."""
    run_vhecfsck_audit_op()
