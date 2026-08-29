#!/usr/bin/env python3
"""AST guard: deny write-shaped calls and SQL under adapters/ and core/.

See ADR-0001 and roadmap ticket P0-09. Exemptions require an inline comment:

    # readonly-ok: <reason>
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT / "vhecfsck" / "adapters", ROOT / "vhecfsck" / "core")

DENIED_ATTRS = frozenset(
    {
        "delete",
        "delete_by_filter",
        "upsert",
        "insert",
        "add",
        "merge_insert",
        "update",
        "drop",
        "create_index",
        "optimize",
        "compact",
        "cleanup_old_versions",
        "restore",
        "commit",
        "execute",
    }
)

DENIED_SQL = (
    "VACUUM",
    "REINDEX",
    "DROP ",
    "DELETE ",
    "UPDATE ",
    "INSERT ",
    "TRUNCATE",
    "ALTER ",
)

EXEMPT_MARKER = "readonly-ok:"


def _line_comment_map(source: str) -> dict[int, str]:
    """Map 1-based line numbers to trailing/full-line comments."""
    comments: dict[int, str] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        if "#" in line:
            comments[i] = line.split("#", 1)[1].strip()
    return comments


def _is_exempt(comments: dict[int, str], lineno: int) -> str | None:
    text = comments.get(lineno, "")
    if EXEMPT_MARKER in text:
        reason = text.split(EXEMPT_MARKER, 1)[1].strip()
        return reason or "(missing reason)"
    return None


def _sql_hit(value: str) -> str | None:
    upper = value.upper()
    for token in DENIED_SQL:
        if token in upper:
            return token.strip()
    return None


def check_file(path: Path) -> tuple[list[str], list[str]]:
    """Return (violations, exemption summaries) for one module."""
    source = path.read_text(encoding="utf-8")
    comments = _line_comment_map(source)
    tree = ast.parse(source, filename=str(path))
    violations: list[str] = []
    exemptions: list[str] = []
    rel = path.relative_to(ROOT)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            attr: str | None = None
            if isinstance(func, ast.Attribute):
                attr = func.attr
            elif isinstance(func, ast.Name):
                # Aliased write: f = tbl.delete; f() — track via prior Assign.
                attr = None
            if attr in DENIED_ATTRS:
                reason = _is_exempt(comments, node.lineno)
                loc = f"{rel}:{node.lineno}: call .{attr}()"
                if reason is not None:
                    exemptions.append(f"{loc} exempt: {reason}")
                else:
                    violations.append(loc)

        if isinstance(node, ast.Assign):
            # f = obj.delete  (store attribute as Name for later Call)
            pass

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            hit = _sql_hit(node.value)
            if hit:
                reason = _is_exempt(comments, node.lineno)
                loc = f"{rel}:{node.lineno}: SQL-like string contains {hit!r}"
                if reason is not None:
                    exemptions.append(f"{loc} exempt: {reason}")
                else:
                    violations.append(loc)

    # Second pass: aliased writes — f = x.delete; f()
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr in DENIED_ATTRS
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases[target.id] = node.value.attr
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in aliases
        ):
            attr = aliases[node.func.id]
            reason = _is_exempt(comments, node.lineno)
            loc = f"{rel}:{node.lineno}: aliased call {node.func.id}() -> .{attr}()"
            if reason is not None:
                exemptions.append(f"{loc} exempt: {reason}")
            else:
                violations.append(loc)

    return violations, exemptions


def main() -> int:
    """Scan adapters/ and core/; exit non-zero on any unexempted violation."""
    all_violations: list[str] = []
    all_exemptions: list[str] = []
    for directory in SCAN_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            violations, exemptions = check_file(path)
            all_violations.extend(violations)
            all_exemptions.extend(exemptions)

    print("readonly-guard: scanned adapters/ and core/")
    if all_exemptions:
        print("exemptions:")
        for item in all_exemptions:
            print(f"  {item}")
    else:
        print("exemptions: none")
    if all_violations:
        print("violations:")
        for item in all_violations:
            print(f"  {item}")
        return 1
    print("ok: no write-shaped calls or denied SQL literals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
