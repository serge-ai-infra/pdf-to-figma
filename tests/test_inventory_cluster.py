"""The clustering primitives everything else in this stage is built from."""

from __future__ import annotations

import pytest

from pdf2figma.inventory.cluster import cluster_points, cluster_scalars


class TestClusterScalars:
    def test_empty_input(self) -> None:
        assert cluster_scalars([], 1.0) == ([], [])

    def test_within_tolerance_merges(self) -> None:
        clusters, assignment = cluster_scalars([12.0, 12.4, 12.8], 1.0)
        assert len(clusters) == 1
        assert assignment == [0, 0, 0]
        assert clusters[0].count == 3
        assert clusters[0].mean == pytest.approx((12.0 + 12.4 + 12.8) / 3)

    def test_beyond_tolerance_splits(self) -> None:
        clusters, assignment = cluster_scalars([12.0, 20.0], 0.5)
        assert len(clusters) == 2
        assert assignment == [0, 1]

    def test_boundary_value_merges_rather_than_splits(self) -> None:
        """Documented behaviour: only strictly *more* than tolerance away splits."""
        clusters, assignment = cluster_scalars([10.0, 10.5], 0.5)
        assert len(clusters) == 1
        assert assignment == [0, 0]

    def test_max_delta_reflects_true_spread(self) -> None:
        values = [10.0, 10.5, 11.0]
        clusters, _ = cluster_scalars(values, 1.0)
        assert len(clusters) == 1
        mean = clusters[0].mean
        assert clusters[0].max_delta == pytest.approx(max(abs(v - mean) for v in values))

    def test_deterministic(self) -> None:
        values = [5.0, 5.2, 9.0, 9.1, 20.0]
        assert cluster_scalars(values, 0.5) == cluster_scalars(values, 0.5)


class TestClusterPoints:
    def test_empty_input(self) -> None:
        assert cluster_points([], 1.0) == ([], [])

    def test_within_tolerance_merges(self) -> None:
        points = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        clusters, assignment = cluster_points(points, 2.0)
        assert len(clusters) == 1
        assert assignment == [0, 0, 0]
        assert clusters[0].count == 3

    def test_beyond_tolerance_splits(self) -> None:
        points = [(0.0, 0.0), (100.0, 100.0)]
        clusters, assignment = cluster_points(points, 1.0)
        assert len(clusters) == 2
        assert assignment == [0, 1]

    def test_higher_frequency_point_anchors_the_centroid(self) -> None:
        """Distinct points are visited by descending frequency, so a repeated
        point seeds the cluster and a rarer nearby point only pulls it a
        little, rather than the reverse.
        """
        points = [(0.0, 0.0)] * 5 + [(1.0, 0.0)]
        clusters, assignment = cluster_points(points, 2.0)
        assert len(clusters) == 1
        assert assignment == [0] * 6
        assert clusters[0].centroid[0] == pytest.approx(1 / 6)

    def test_max_delta_uses_final_centroid_not_assignment_time_centroid(self) -> None:
        points = [(0.0, 0.0), (0.0, 0.0), (3.0, 0.0)]
        clusters, _ = cluster_points(points, 5.0)
        assert len(clusters) == 1
        cx = clusters[0].centroid[0]
        assert clusters[0].max_delta == pytest.approx(max(abs(0.0 - cx), abs(3.0 - cx)))

    def test_deterministic(self) -> None:
        points = [(0.0, 0.0), (0.5, 0.5), (10.0, 10.0)]
        assert cluster_points(points, 1.0) == cluster_points(points, 1.0)
