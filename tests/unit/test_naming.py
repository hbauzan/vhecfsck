"""P0-13: canonical lowercase name surfaces."""

from __future__ import annotations

import re
from pathlib import Path

import vhecfsck

ROOT = Path(__file__).resolve().parents[2]

# Technical identifiers must be lowercase vhecfsck (ADR-0012).
_BANNED = re.compile(r"\bVecFsck\b|\bvecfsck\b|\bVHECFSCK\b")


def test_package_name_is_lowercase_vhecfsck() -> None:
    assert vhecfsck.__name__ == "vhecfsck"


def test_pyproject_urls_point_at_canonical_repo() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "vhecfsck"' in text
    assert "https://github.com/hbauzan/vhecfsck" in text
    assert "Homepage" in text
    assert "Repository" in text
    assert "Issues" in text
    assert "Changelog" in text


def test_no_banned_spellings_in_package_tree() -> None:
    hits: list[str] = []
    for path in (ROOT / "vhecfsck").rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _BANNED.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()}")
    assert not hits, "banned spellings:\n" + "\n".join(hits)


def test_public_copy_states_h_is_hector() -> None:
    """ADR-0012: H is Hector (wordplay), not an invented acronym."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    home = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    for label, text in (("README.md", readme), ("docs/index.md", home)):
        assert "Hector" in text, f"{label} must name Hector"
        assert "fsck" in text, f"{label} must keep the fsck analogy"
