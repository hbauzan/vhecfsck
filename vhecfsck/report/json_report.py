"""Deterministic JSON serialization and JSON Schema generator for audit reports (P3-02).

Design Rationale (Cross-Platform Byte Identity):
1. Float Rounding (6 decimals): ARM (Apple Silicon) and x86_64 (Linux) CPU vector
   instructions can differ in the least significant float bits. Rounding floats at
   the serialization boundary guarantees byte-identical JSON across platforms.
2. Key Sorting: Alphabetically sorted dict keys eliminate key order instability.
3. Unix Line Endings (\n): Explicit \\n with a single trailing newline ensures
   POSIX compliance and stable checksums (sha256) regardless of OS git settings.
"""

from __future__ import annotations

import json
from typing import Any

from vhecfsck.models.report import Report, report_to_dict

_FLOAT_PRECISION: int = 6


def _normalize_for_json(obj: Any) -> Any:
    """Recursively round floats to 6 decimal places and sort dict keys."""
    if isinstance(obj, float):
        return round(obj, _FLOAT_PRECISION)
    if isinstance(obj, dict):
        return {
            str(k): _normalize_for_json(v)
            for k, v in sorted(obj.items(), key=lambda item: str(item[0]))
        }
    if isinstance(obj, list):
        return [_normalize_for_json(item) for item in obj]
    if isinstance(obj, tuple):
        return [_normalize_for_json(item) for item in obj]
    return obj


def render_json(report: Report, indent: int | None = 2) -> str:
    """Render a Report object to a deterministic, byte-identical JSON string.

    Args:
        report: The Report instance to serialize.
        indent: Indentation level (default: 2 spaces). If None, emits compact JSON.

    Returns:
        Deterministic JSON string with Unix \\n line endings and single trailing
        newline.
    """
    raw_dict = report_to_dict(report)
    normalized = _normalize_for_json(raw_dict)

    rendered = json.dumps(
        normalized,
        indent=indent,
        ensure_ascii=False,
    )

    # Normalize CRLF to LF and ensure single trailing newline
    lines = rendered.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(lines).rstrip("\n") + "\n"


def generate_report_schema() -> dict[str, Any]:
    """Generate the published JSON Schema for the Report model."""
    schema = Report.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema
