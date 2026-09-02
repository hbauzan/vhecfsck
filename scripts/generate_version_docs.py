#!/usr/bin/env python3
"""Inject the pyproject version into the docs homepage (P9-14).

Derives ``[project].version`` at docs-build time. Do not type a release number
into ``docs/index.md`` by hand — that is the same coupling that bit the golden
fixtures. Also ensures ``docs/changelog.md`` is a view of root ``CHANGELOG.md``
(symlink if present, generated copy otherwise).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "docs" / "index.md"
CHANGELOG_SRC = ROOT / "CHANGELOG.md"
CHANGELOG_DEST = ROOT / "docs" / "changelog.md"
PYPROJECT_PATH = ROOT / "pyproject.toml"

VERSION_BEGIN = "<!-- version:begin -->"
VERSION_END = "<!-- version:end -->"


def read_project_version() -> str:
    """Return ``[project].version`` from ``pyproject.toml``."""
    with PYPROJECT_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    version = data["project"]["version"]
    if not isinstance(version, str) or not version:
        msg = "pyproject.toml [project].version is missing or not a string"
        raise ValueError(msg)
    return version


def version_markup(version: str) -> str:
    """Homepage fragment. ``version`` must come from ``read_project_version``."""
    pypi = f"https://pypi.org/project/vhecfsck/{version}/"
    return (
        f"Current release: [{version}](changelog.md) · [PyPI]({pypi}).\n"
        "On GitHub Pages the changelog is `/changelog` (no trailing slash). "
        "`/changelog/` 404s, same as `/releasing/` versus `/releasing`."
    )


def inject_version(index_text: str, version: str) -> str:
    """Replace the delimited region in ``docs/index.md`` with ``version`` markup."""
    begin = index_text.find(VERSION_BEGIN)
    end = index_text.find(VERSION_END)
    if begin < 0 or end < 0 or end <= begin:
        msg = (
            f"{INDEX_PATH} must contain {VERSION_BEGIN} ... {VERSION_END} "
            "markers for the generated version line"
        )
        raise ValueError(msg)
    inner_start = begin + len(VERSION_BEGIN)
    fragment = f"\n{version_markup(version)}\n"
    return index_text[:inner_start] + fragment + index_text[end:]


def ensure_changelog() -> None:
    """Keep ``docs/changelog.md`` as a view of the root changelog, not a second original."""
    src_text = CHANGELOG_SRC.read_text(encoding="utf-8")
    if CHANGELOG_DEST.is_symlink():
        resolved = CHANGELOG_DEST.resolve()
        if resolved == CHANGELOG_SRC.resolve():
            return
    CHANGELOG_DEST.write_text(src_text, encoding="utf-8")


def generate_version_docs() -> str:
    """Rewrite the homepage region and sync the changelog page. Return new index text."""
    version = read_project_version()
    updated = inject_version(INDEX_PATH.read_text(encoding="utf-8"), version)
    INDEX_PATH.write_text(updated, encoding="utf-8")
    ensure_changelog()
    return updated


if __name__ == "__main__":
    import subprocess

    generate_version_docs()
    subprocess.run(["uv", "run", "ruff", "format", str(INDEX_PATH)], check=False)
    print(f"Successfully generated version region in {INDEX_PATH}")
    print(f"Changelog page: {CHANGELOG_DEST}")
