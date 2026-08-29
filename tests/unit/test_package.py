"""Package bootstrap: version single-sourcing and lazy-import discipline."""

from __future__ import annotations

import importlib
import re
import sys
from importlib.metadata import version

# PEP 440 public version identifiers (core + common pre/post/dev segments).
_PEP440 = re.compile(
    r"^"
    r"(?:[1-9][0-9]*!)?"
    r"(?:0|[1-9][0-9]*)"
    r"(?:\.(?:0|[1-9][0-9]*))*"
    r"(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?"
    r"(?:\.post(?:0|[1-9][0-9]*))?"
    r"(?:\.dev(?:0|[1-9][0-9]*))?"
    r"(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?"
    r"$",
    re.IGNORECASE,
)


def test_version_is_pep440_and_matches_metadata() -> None:
    import vhecfsck

    assert _PEP440.fullmatch(vhecfsck.__version__), vhecfsck.__version__
    assert vhecfsck.__version__ == version("vhecfsck")


def test_importing_package_does_not_import_numpy() -> None:
    for name in list(sys.modules):
        if name == "numpy" or name.startswith("numpy."):
            del sys.modules[name]
        if name == "vhecfsck" or name.startswith("vhecfsck."):
            del sys.modules[name]

    importlib.invalidate_caches()
    import vhecfsck  # noqa: F401

    assert "numpy" not in sys.modules
