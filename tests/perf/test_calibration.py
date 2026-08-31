# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""P8-01 calibration harness — nightly/perf seam.

The default gate covers the smoke profile in ``tests/unit/test_calibration_harness.py``.
This module exists so ``make verify-full`` still collects a perf-marked check that
the smoke harness completes without inventing metric values.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.calibrate import PROFILE_SMOKE, run_profile


@pytest.mark.perf
def test_smoke_calibration_profile_completes(tmp_path: Path) -> None:
    result = run_profile(PROFILE_SMOKE, out_dir=tmp_path, cache_dir=tmp_path / "cache")
    assert result.results_csv.is_file()
    header = result.results_csv.read_text(encoding="utf-8").splitlines()[0]
    assert "unavailable_reason" in header
