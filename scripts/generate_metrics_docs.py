#!/usr/bin/env python3
"""Programmatic Metrics Reference documentation generator (P9-02).

Reads `roadmap/02-metrics-spec.md` and generates `docs/metrics.md` with section citations.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "roadmap" / "02-metrics-spec.md"
OUTPUT_PATH = ROOT / "docs" / "metrics.md"


def generate_metrics_docs() -> str:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")

    # Fix relative links to ADRs and phases for MkDocs rendering
    spec_text = re.sub(
        r"\]\(adr/([^\)]+)\)",
        r"](https://github.com/hbauzan/vhecfsck/blob/main/roadmap/adr/\1)",
        spec_text,
    )
    spec_text = re.sub(
        r"\]\(phases/([^\)]+)\)",
        r"](https://github.com/hbauzan/vhecfsck/blob/main/roadmap/phases/\1)",
        spec_text,
    )

    lines: list[str] = [
        "# Metrics Reference Specification",
        "",
        "> **Single Source of Truth**: This reference is programmatically generated from [`roadmap/02-metrics-spec.md`](https://github.com/hbauzan/vhecfsck/blob/main/roadmap/02-metrics-spec.md).",
        "> Every metric definition cites its normative section in `02-metrics-spec.md`.",
        "",
        "## Summary of Core Metrics",
        "",
        "| Metric | Target Pathology | Warn Threshold | Fail Threshold | Direction | Normative Spec Section |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
        "| **Canary Recall** | Silent recall decay | `< 0.85` | `< 0.70` | Lower is worse | `02-metrics-spec.md` §2.1 |",
        "| **Hub Share (top 1%)** | Hubness / central point dominance | `> 0.20` | `> 0.35` | Higher is worse | `02-metrics-spec.md` §3.1 |",
        "| **Antihub Fraction** | Orphaning / unreachable vectors | `> 0.25` | `> 0.40` | Higher is worse | `02-metrics-spec.md` §3.2 |",
        "| **Deletion Fragmentation Index (DFI)** | Tombstone accumulation | `> 0.15` | `> 0.30` | Higher is worse | `02-metrics-spec.md` §4.1 |",
        "| **Partition Size CV** | IVF centroid imbalance / skew | `> 1.20` | `> 2.00` | Higher is worse | `02-metrics-spec.md` §5.1 |",
        "",
        "---",
        "",
    ]

    in_header = True
    for line in spec_text.splitlines():
        if line.startswith("# 02 — Metrics Specification"):
            continue
        if in_header and line.startswith("## "):
            in_header = False
        if not in_header:
            if line.startswith("## "):
                sec_title = line[3:].strip()
                lines.append(f"## {sec_title}")
                lines.append("")
                lines.append(f"> *Cites `roadmap/02-metrics-spec.md` — {sec_title}*")
                lines.append("")
                continue
            if line.startswith("### "):
                sec_title = line[4:].strip()
                lines.append(f"### {sec_title}")
                lines.append("")
                lines.append(f"> *Cites `roadmap/02-metrics-spec.md` — {sec_title}*")
                lines.append("")
                continue
            lines.append(line)

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import subprocess

    content = generate_metrics_docs()
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    subprocess.run(["uv", "run", "ruff", "format", str(OUTPUT_PATH)], check=False)
    print(f"Successfully generated {OUTPUT_PATH}")
