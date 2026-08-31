"""Palette, marker and contrast invariants for the visualizer theme (P6-08)."""

from __future__ import annotations

import itertools

import pytest
from vhecfsck.models.scene import (
    CLASS_MARKERS,
    CLASS_SIZE_SCALE,
    DEFAULT_PALETTE_NAME,
    PALETTES,
    PointClass,
    contrast_ratio,
    relative_luminance,
    resolve_palette,
)

#: Minimum greyscale separation between the two classes the phase exists to
#: explain. A design constraint on the palette, not a measured budget.
MIN_HUB_ANTIHUB_CONTRAST = 1.5


def test_every_palette_covers_every_class() -> None:
    for name, palette in PALETTES.items():
        missing = set(PointClass) - set(palette)
        assert not missing, f"palette {name} is missing {missing}"


def test_palette_colours_are_distinct_within_a_palette() -> None:
    for name, palette in PALETTES.items():
        colours = [c.lower() for c in palette.values()]
        assert len(set(colours)) == len(colours), f"duplicate colour in {name}"


def test_every_class_has_a_distinct_marker() -> None:
    """Class is never conveyed by hue alone: shape is a full second channel."""
    markers = list(CLASS_MARKERS.values())

    assert set(CLASS_MARKERS) == set(PointClass)
    assert len(set(markers)) == len(markers)


def test_every_class_has_a_size_scale() -> None:
    assert set(CLASS_SIZE_SCALE) == set(PointClass)
    assert all(v > 0 for v in CLASS_SIZE_SCALE.values())


def test_healthy_is_the_smallest_class_so_findings_read_first() -> None:
    healthy = CLASS_SIZE_SCALE[PointClass.HEALTHY]

    assert healthy == min(CLASS_SIZE_SCALE.values())
    assert CLASS_SIZE_SCALE[PointClass.HUB] > healthy


def test_deuteranopia_palette_separates_hub_from_antihub_in_greyscale() -> None:
    palette = PALETTES["deuteranopia"]

    ratio = contrast_ratio(palette[PointClass.HUB], palette[PointClass.ANTIHUB])

    assert ratio >= MIN_HUB_ANTIHUB_CONTRAST


def test_no_two_classes_share_both_hue_and_marker() -> None:
    for palette in PALETTES.values():
        for a, b in itertools.combinations(PointClass, 2):
            same_hue = palette[a].lower() == palette[b].lower()
            same_marker = CLASS_MARKERS[a] is CLASS_MARKERS[b]
            assert not (same_hue and same_marker)


def test_resolve_palette_returns_the_named_palette() -> None:
    assert resolve_palette("deuteranopia") is PALETTES["deuteranopia"]
    assert resolve_palette(DEFAULT_PALETTE_NAME) is PALETTES["default"]


def test_resolve_palette_names_the_known_palettes_when_it_fails() -> None:
    with pytest.raises(KeyError, match="deuteranopia"):
        resolve_palette("nope")


def test_relative_luminance_anchors() -> None:
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#ffffff") == pytest.approx(1.0)
    assert relative_luminance("808080") == pytest.approx(0.2159, abs=1e-3)


def test_contrast_ratio_is_symmetric_and_bounded() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=1e-6)
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0, abs=1e-6)
    assert contrast_ratio("#123456", "#123456") == pytest.approx(1.0)


def test_relative_luminance_rejects_a_malformed_colour() -> None:
    with pytest.raises(ValueError, match="rrggbb"):
        relative_luminance("#fff")
