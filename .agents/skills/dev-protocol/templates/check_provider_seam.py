#!/usr/bin/env python3
"""Static guard: provider SDKs may only be imported inside the adapter layer.

Makes the single-provider-interface rule from dev-protocol/SKILL.md §3.2 mechanical
instead of aspirational. See dev-protocol/guardrails.md §5.

Why an AST walk and not a regex: a regex reports hits inside strings and comments,
and misses the case that actually matters — an aliased or dynamic import. This walks
the tree, so `importlib.import_module("openai")` is caught and the word "openai"
inside a docstring is not.

Usage in a new app:
    1. Copy to `scripts/check_provider_seam.py`.
    2. Edit the CONFIG block below — nothing else should need changing.
    3. Wire into `make verify` (target `guards`) and `.pre-commit-config.yaml`.
    4. Break it once on purpose and confirm the build fails (guardrails.md §5.3).

    uv run python scripts/check_provider_seam.py [PATH ...]

Exemptions:
    Append `# seam-ok: <reason>` to the offending line, or put it on the line above.
    The reason is mandatory and every exemption is printed in the summary, so they
    stay visible instead of accumulating quietly.

Exit codes follow dev-protocol/code-design.md §4:
    0 OK · 2 FAIL (violations found) · 4 USAGE (bad arguments)
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# CONFIG — the only part you edit per repo
# =============================================================================

# Directory names that constitute the adapter layer. Provider SDKs are allowed
# here and nowhere else. Matched against any path segment.
ADAPTER_DIRS: frozenset[str] = frozenset({"adapters", "providers"})

# Top-level module names of provider SDKs. Submodules are covered automatically
# (`openai.types` matches `openai`). Add whatever your app can reach.
PROVIDER_SDKS: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "google",  # google.generativeai / google.genai
        "cohere",
        "mistralai",
        "groq",
        "ollama",
        "llama_cpp",
        "vllm",
        "transformers",
        "huggingface_hub",
        "litellm",
        "boto3",  # bedrock
    }
)

# Never walked.
SKIP_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".mypy_cache"}
)

# Searched when no path is given on the command line.
DEFAULT_ROOTS: tuple[str, ...] = ("src", "app", "scripts")

# Note on tests/: they are checked like any other code, deliberately. SKILL.md §3.2
# says tests mock the provider interface rather than the SDK, so a direct SDK import
# in a test should cost an explicit `# seam-ok:`. Add "tests" to SKIP_DIRS to opt out.

# =============================================================================

EXEMPTION_RE = re.compile(r"#\s*seam-ok:\s*(?P<reason>\S.*)$")

OK, FAIL, USAGE = 0, 2, 4


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    sdk: str
    detail: str
    reason: str | None  # set when an exemption comment covers this line


def _top_level(module: str | None) -> str:
    return (module or "").split(".", 1)[0]


def _in_adapter_layer(path: Path) -> bool:
    return any(part in ADAPTER_DIRS for part in path.parts)


def _exemption_for(lines: list[str], lineno: int) -> str | None:
    """An exemption applies on the offending line or the line directly above it."""
    for candidate in (lineno - 1, lineno - 2):
        if 0 <= candidate < len(lines):
            match = EXEMPTION_RE.search(lines[candidate])
            if match:
                return match.group("reason").strip()
    return None


def _string_arg(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def _dynamic_import_target(node: ast.Call) -> str | None:
    """Return the module named by importlib.import_module(...) or __import__(...)."""
    func = node.func
    if isinstance(func, ast.Name) and func.id == "__import__":
        return _string_arg(node)
    if isinstance(func, ast.Attribute) and func.attr == "import_module":
        return _string_arg(node)
    return None


def scan_file(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        print(f"{path}:{exc.lineno}: could not parse: {exc.msg}", file=sys.stderr)
        return []

    lines = source.splitlines()
    findings: list[Finding] = []

    def record(lineno: int, sdk: str, detail: str) -> None:
        findings.append(Finding(path, lineno, sdk, detail, _exemption_for(lines, lineno)))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                sdk = _top_level(alias.name)
                if sdk in PROVIDER_SDKS:
                    record(node.lineno, sdk, f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            sdk = _top_level(node.module)
            if sdk in PROVIDER_SDKS:
                record(node.lineno, sdk, f"from {node.module} import ...")
        elif isinstance(node, ast.Call):
            target = _dynamic_import_target(node)
            sdk = _top_level(target)
            if target and sdk in PROVIDER_SDKS:
                record(node.lineno, sdk, f"dynamic import of {target!r}")

    return findings


def iter_python_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        for path in sorted(root.rglob("*.py")):
            if not any(part in SKIP_DIRS for part in path.parts):
                files.append(path)
    return files


def main(argv: list[str]) -> int:
    if any(arg.startswith("-") for arg in argv):
        print(__doc__, file=sys.stderr)
        return USAGE

    given = [Path(a) for a in argv] or [Path(d) for d in DEFAULT_ROOTS]
    roots = [p for p in given if p.exists()]
    if not roots:
        print(
            "check_provider_seam: no source roots found; set DEFAULT_ROOTS or pass a path",
            file=sys.stderr,
        )
        return USAGE

    violations: list[Finding] = []
    exemptions: list[Finding] = []

    for path in iter_python_files(roots):
        if _in_adapter_layer(path):
            continue
        for finding in scan_file(path):
            (exemptions if finding.reason else violations).append(finding)

    if exemptions:
        print(f"provider-seam exemptions in force ({len(exemptions)}):")
        for finding in exemptions:
            print(f"  {finding.path}:{finding.line}  {finding.sdk} — {finding.reason}")
        print()
        sys.stdout.flush()

    for finding in violations:
        print(
            f"{finding.path}:{finding.line}: provider SDK {finding.sdk!r} outside the adapter "
            f"layer ({finding.detail}). Route it through the provider interface, or annotate "
            f"with `# seam-ok: <reason>`.",
            file=sys.stderr,
        )

    if violations:
        print(f"\nprovider-seam: {len(violations)} violation(s).", file=sys.stderr)
        return FAIL

    print(f"provider-seam: clean ({len(exemptions)} exemption(s)).")
    return OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
