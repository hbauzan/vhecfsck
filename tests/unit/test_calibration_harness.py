# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""P8-01: calibration harness contracts (schema, licences, smoke, skips)."""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.calibrate import (
    CATALOG,
    FIVE_METRICS,
    PROFILE_SMOKE,
    parse_glove_lines,
    read_fvecs,
    run_profile,
    write_fvecs,
)

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_records_a_licence_for_every_dataset() -> None:
    assert CATALOG, "catalog must not be empty"
    ids: list[str] = []
    for spec in CATALOG:
        ids.append(spec.id)
        assert spec.licence.strip(), spec.id
        assert spec.provenance.strip(), spec.id
        assert spec.spdx.strip(), spec.id
        assert spec.family in {"gaussian", "public", "synthetic"}
    assert len(ids) == len(set(ids))


def test_nytimes_is_excluded_under_r13() -> None:
    nyt = next(s for s in CATALOG if s.id == "nytimes-256")
    assert nyt.status == "excluded"
    assert "LDC" in nyt.licence or "LDC" in nyt.notes


def test_smoke_csv_has_five_metrics_and_empty_unavailable_value(
    tmp_path: Path,
) -> None:
    result = run_profile(PROFILE_SMOKE, out_dir=tmp_path, cache_dir=tmp_path / "cache")
    rows = _read_csv(result.results_csv)
    assert rows, "smoke must emit at least one row"
    metric_ids = {row["metric_id"] for row in rows if row["kind"] == "baseline"}
    assert metric_ids >= FIVE_METRICS
    for row in rows:
        if row["state"] == "UNAVAILABLE":
            assert row["value"] == "", row
            assert row["unavailable_reason"].strip(), row
        else:
            assert row["value"] != "", row
            parsed = float(row["value"])
            assert parsed == parsed  # not NaN


def test_smoke_two_runs_are_byte_identical(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    run_profile(PROFILE_SMOKE, out_dir=a, cache_dir=tmp_path / "cache")
    run_profile(PROFILE_SMOKE, out_dir=b, cache_dir=tmp_path / "cache")
    left = a.joinpath("results.csv").read_bytes()
    right = b.joinpath("results.csv").read_bytes()
    assert left == right
    assert (
        a.joinpath("hubness_sensitivity.csv").read_bytes()
        == b.joinpath("hubness_sensitivity.csv").read_bytes()
    )


def test_hubness_sensitivity_covers_smoke_grid(tmp_path: Path) -> None:
    result = run_profile(PROFILE_SMOKE, out_dir=tmp_path, cache_dir=tmp_path / "cache")
    rows = _read_csv(result.sensitivity_csv)
    pairs = {(int(r["hubness_sample_size"]), int(r["k_hub"])) for r in rows}
    expected = {
        (s, k) for s in PROFILE_SMOKE.hubness_sample_sizes for k in PROFILE_SMOKE.k_hubs
    }
    assert expected <= pairs
    for row in rows:
        if row["hub_share_top1pct"] == "":
            assert row["hub_share_state"] == "UNAVAILABLE"
            assert row["hub_share_reason"].strip()
        else:
            float(row["hub_share_top1pct"])
            float(row["antihub_fraction"])


def test_write_and_read_fvecs_match(tmp_path: Path) -> None:
    import numpy as np

    src = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    path = tmp_path / "round.fvecs"
    write_fvecs(path, src)
    got = read_fvecs(path)
    assert got.tobytes() == src.tobytes()


def test_parse_glove_lines_takes_prefix() -> None:
    text = "the 1.0 0.0\na 0.0 1.0\nan 0.5 0.5\n"
    vectors, _tokens = parse_glove_lines(text.splitlines(), max_vectors=2)
    assert vectors.shape == (2, 2)


def test_missing_public_dataset_is_skip_not_a_number(tmp_path: Path) -> None:
    """Public corpora that are not in cache must not mint a fake 0.0 metric."""
    from dataclasses import replace

    from scripts.calibrate import PROFILE_SMOKE as SMOKE

    profile = replace(SMOKE, include_public=True, public_ids=("sift-128",))
    result = run_profile(profile, out_dir=tmp_path, cache_dir=tmp_path / "empty-cache")
    skipped = _read_csv(result.skipped_csv)
    assert skipped
    assert any(row["dataset_id"] == "sift-128" for row in skipped)
    for row in skipped:
        assert row["reason"].strip()
    baseline = _read_csv(result.results_csv)
    assert not any(row["dataset_id"] == "sift-128" for row in baseline)


def test_committed_datasets_md_lists_catalog() -> None:
    text = (ROOT / "docs" / "calibration" / "datasets.md").read_text(encoding="utf-8")
    for spec in CATALOG:
        assert spec.id in text, spec.id


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
