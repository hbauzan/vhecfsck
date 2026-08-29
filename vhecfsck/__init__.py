"""vhecfsck — topological audit for vector indexes.

Public package surface is intentionally tiny: only ``__version__``.
Heavy imports (numpy, adapters, metrics) stay out of this module so
``import vhecfsck`` stays cheap for CLI startup.
"""

from __future__ import annotations

from importlib.metadata import version

__version__ = version("vhecfsck")

__all__ = ["__version__"]
