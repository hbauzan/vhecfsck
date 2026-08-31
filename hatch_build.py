"""Custom hatchling build hook for building the SPA visualizer front-end."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:

    class BuildHookInterface:  # type: ignore[no-redef]  # Fallback stub when hatchling is not installed.
        """Fallback interface for build hook."""

        root: str


class CustomBuildHook(BuildHookInterface):
    """Hatchling custom build hook that compiles the SPA in vhecfsck/web."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Run frontend build before creating wheel / sdist."""
        del version, build_data
        root = Path(self.root)
        web_dir = root / "vhecfsck" / "web"
        dist_dir = web_dir / "dist"
        dist_index = dist_dir / "index.html"

        if dist_index.is_file():
            return

        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError(
                "npm is required to build vhecfsck web assets, "
                "but npm was not found on PATH."
            )

        node_modules = web_dir / "node_modules"
        if not node_modules.is_dir():
            subprocess.run([npm, "ci"], cwd=web_dir, check=True)
        subprocess.run([npm, "run", "build"], cwd=web_dir, check=True)

        if not dist_index.is_file():
            raise RuntimeError(f"SPA build completed but {dist_index} is missing.")
