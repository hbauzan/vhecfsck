#!/usr/bin/env python3
"""Codebase context dumper for vhecfsck.

Generates `vhecfsck.txt` at the repository root containing all pertinent tool source code,
configuration, tests, scripts, and documentation for AI agent context.
Verifies if `vhecfsck.txt` exists and removes it before building a fresh dump.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Top-level root files to include explicitly if they exist
ROOT_FILES = (
    "AGENTS.md",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "NOTICE",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
    "Makefile",
    "setup.sh",
    "hatch_build.py",
    "mkdocs.yml",
)

# Relative directory trees to search recursively
SOURCE_DIRS = (
    "vhecfsck",
    "scripts",
    "roadmap",
    "docs",
    "examples",
    "schema",
)

# Directories to exclude from recursive traversal
IGNORED_DIRS = {
    ".git",
    ".venv",
    ".worktrees",
    ".agents",
    ".claude",
    ".cursor",
    ".vscode",
    ".github",
    "tests",
    "playwright-report",
    "blob-report",
    "coverage",
    ".cache",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".import_linter_cache",
    ".hypothesis",
    "dist",
    "site",
    "node_modules",
    "build",
    "test-results",
}

# Specific files to ignore
IGNORED_FILES = {
    "vhecfsck.txt",
    ".DS_Store",
    "coverage.xml",
    "uv.lock",
    "pnpm-lock.yaml",
    "package-lock.json",
}

# Binary / non-text file extensions to skip
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".7z",
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".wav",
    ".ogg",
}


def is_text_file(path: Path) -> bool:
    """Determine whether a file is a readable text file."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return False
    try:
        with path.open(encoding="utf-8") as f:
            f.read(4096)
        return True
    except (UnicodeDecodeError, PermissionError, OSError):
        return False


def collect_dump_files(root_dir: Path) -> list[Path]:
    """Collect relative paths of all pertinent codebase files for the dump."""
    collected: list[Path] = []
    seen: set[Path] = set()

    # 1. Root files
    for filename in ROOT_FILES:
        rel = Path(filename)
        full = root_dir / rel
        if full.is_file() and rel not in seen and is_text_file(full):
            collected.append(rel)
            seen.add(rel)

    # 2. Source directories
    for dir_name in SOURCE_DIRS:
        source_dir = root_dir / dir_name
        if not source_dir.is_dir():
            continue
        for current_root, dirs, files in os.walk(source_dir):
            # Exclude ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for file_name in sorted(files):
                if file_name in IGNORED_FILES:
                    continue
                full_path = Path(current_root) / file_name
                rel_path = full_path.relative_to(root_dir)
                if rel_path in seen:
                    continue
                if is_text_file(full_path):
                    collected.append(rel_path)
                    seen.add(rel_path)

    return sorted(collected)


def generate_dump(root_dir: Path | None = None) -> int:
    """Verify vhecfsck.txt existence, remove if present, and write fresh codebase dump."""
    target_root = (root_dir or ROOT).resolve()
    output_file = target_root / "vhecfsck.txt"

    if output_file.exists():
        print(f"[dump-context] Existing {output_file.name} found. Removing...")
        output_file.unlink()

    files = collect_dump_files(target_root)
    print(f"[dump-context] Collecting {len(files)} files for AI context dump...")

    lines_out: list[str] = [
        "=" * 80,
        "VHECFSCK CODEBASE CONTEXT DUMP",
        "Generated for AI Agent Analysis",
        f"Target Output: {output_file.name}",
        "=" * 80,
        "",
        "MANIFEST OF INCLUDED FILES:",
    ]

    for rel_path in files:
        lines_out.append(f"  - {rel_path}")

    lines_out.extend(["", "=" * 80, "FILE CONTENTS", "=" * 80, ""])

    file_count = 0
    total_bytes = 0

    for rel_path in files:
        full_path = target_root / rel_path
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            print(f"[dump-context] Warning: Could not read {rel_path}: {err}")
            continue

        file_count += 1
        total_bytes += len(content.encode("utf-8"))

        lines_out.append("=" * 80)
        lines_out.append(f"FILE: {rel_path}")
        lines_out.append("=" * 80)
        lines_out.append(content)
        if not content.endswith("\n"):
            lines_out.append("")
        lines_out.append("")

    lines_out.append("=" * 80)
    lines_out.append(f"END OF DUMP: {file_count} files, {total_bytes} bytes")
    lines_out.append("=" * 80)
    lines_out.append("")

    output_file.write_text("\n".join(lines_out), encoding="utf-8")
    print(
        f"[dump-context] Successfully created {output_file.name} "
        f"({file_count} files, {total_bytes} bytes)."
    )
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    raise SystemExit(generate_dump(target))
