"""Perceptual diff: cropping and comparison against synthetic images.

Built directly as numpy arrays — `load_rgb`'s job is only turning a file into
exactly this shape, no need to round-trip through disk to test the cropping
and comparison logic itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from pdf2figma.verify import compare, crop_region, diff_perceptual
from tests.fixtures import synthetic_ir as fx

WHITE = (255.0, 255.0, 255.0)
BLUE = (51.0, 85.0, 255.0)
RED = (200.0, 17.0, 17.0)


def canvas(width: int, height: int, color: tuple[float, float, float] = WHITE) -> np.ndarray:
    arr = np.empty((height, width, 3), dtype=np.float64)
    arr[:, :] = color
    return arr


def paint(
    arr: np.ndarray, x: int, y: int, w: int, h: int, color: tuple[float, float, float]
) -> None:
    arr[y : y + h, x : x + w] = color


class TestCropRegion:
    def test_dpi_scales_points_to_pixels(self) -> None:
        img = canvas(400, 400)
        bbox = fx.BBox(x=10, y=10, w=50, h=50)
        crop_72 = crop_region(img, bbox, dpi=72)
        crop_144 = crop_region(img, bbox, dpi=144)
        assert crop_72.array is not None and crop_72.array.shape[:2] == (50, 50)
        assert crop_144.array is not None and crop_144.array.shape[:2] == (100, 100)

    def test_degenerate_bbox_is_noted_not_crashed(self) -> None:
        img = canvas(200, 200)
        line = fx.BBox(x=0, y=0, w=100, h=0)
        result = crop_region(img, line, dpi=72)
        assert result.status == "degenerate"
        assert result.array is None
        assert result.note is not None

    def test_out_of_bounds_bbox_is_noted_not_crashed(self) -> None:
        img = canvas(100, 100)
        outside = fx.BBox(x=90, y=90, w=50, h=50)
        result = crop_region(img, outside, dpi=72)
        assert result.status == "out-of-bounds"
        assert result.array is None
        assert result.note is not None


class TestDiffPerceptual:
    def test_matching_region_scores_100_percent(self) -> None:
        reference = canvas(200, 200)
        candidate = canvas(200, 200)
        node = fx.rect_node("r1", 0, 0, 100, 50, fill=fx.CARD_FILL)
        paint(reference, 0, 0, 100, 50, BLUE)
        paint(candidate, 0, 0, 100, 50, BLUE)

        report = diff_perceptual(reference, candidate, [node], dpi=72, threshold=8)
        assert report.regions[0].status == "compared"
        assert report.regions[0].match_pct == pytest.approx(100.0)

    def test_difference_is_isolated_to_its_own_region(self) -> None:
        reference = canvas(200, 200)
        candidate = canvas(200, 200)
        matching = fx.rect_node("r1", 0, 0, 100, 50, fill=fx.CARD_FILL)
        broken = fx.rect_node("r2", 0, 60, 100, 20, fill=fx.HEADER_COLOR)

        paint(reference, 0, 0, 100, 50, BLUE)
        paint(candidate, 0, 0, 100, 50, BLUE)
        paint(reference, 0, 60, 100, 20, (17.0, 17.0, 17.0))
        paint(candidate, 0, 60, 100, 20, RED)

        report = diff_perceptual(reference, candidate, [matching, broken], dpi=72, threshold=8)
        by_id = {r.id: r for r in report.regions}
        assert by_id["r1"].match_pct == pytest.approx(100.0)
        assert by_id["r2"].match_pct == pytest.approx(0.0)

    def test_degenerate_region_is_reported_not_dropped(self) -> None:
        reference = canvas(200, 200)
        candidate = canvas(200, 200)
        line = fx.shape_node("l1", "line", 0, 0, 100, 0, fill=None)

        report = diff_perceptual(reference, candidate, [line], dpi=72, threshold=8)
        assert len(report.regions) == 1
        assert report.regions[0].status == "degenerate"
        assert report.regions[0].match_pct is None

    def test_out_of_bounds_region_is_reported_not_dropped(self) -> None:
        reference = canvas(100, 100)
        candidate = canvas(100, 100)
        outside = fx.rect_node("far", 90, 90, 50, 50, fill="#000000")

        report = diff_perceptual(reference, candidate, [outside], dpi=72, threshold=8)
        assert report.regions[0].status == "out-of-bounds"

    def test_overall_whole_image_metrics_are_still_reported(self) -> None:
        reference = canvas(50, 50)
        candidate = canvas(50, 50)
        paint(candidate, 0, 0, 10, 10, RED)

        report = diff_perceptual(reference, candidate, [], dpi=72, threshold=8)
        assert report.overall.match_pct < 100.0
        assert report.overall.differing_px == 100


class TestCompare:
    def test_identical_images_are_a_perfect_match(self) -> None:
        img = canvas(20, 20)
        metrics = compare(img, img.copy(), threshold=8)
        assert metrics["match_pct"] == pytest.approx(100.0)
        assert metrics["mae"] == pytest.approx(0.0)
