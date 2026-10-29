"""Tolerance clustering — the one thing every token and candidate is built from.

Two primitives cover all of it: a single-pass 1-D walk for scalars (font size,
spacing gaps) and a greedy nearest-centroid walk for points in an arbitrary
number of dimensions (colors in 3-D, shape width/height in 2-D). Neither is
globally optimal; both are deterministic given their input, and both report
`max_delta` so a reader can see what merging actually cost rather than trust
that it was reasonable.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ScalarCluster:
    mean: float
    count: int
    max_delta: float


def cluster_scalars(
    values: Sequence[float], tolerance: float
) -> tuple[list[ScalarCluster], list[int]]:
    """Sort ascending, walk once, split when a value is more than `tolerance`
    from the current cluster's running mean.

    Deterministic and O(n log n). Boundary-sensitive by construction: a value
    sitting exactly at the tolerance edge between two real groups lands in
    whichever the scan reaches first, not "the correct" one by any
    independent standard.

    Returns `(clusters, assignment)` where `assignment[i]` is the index into
    `clusters` that `values[i]` landed in.
    """
    if not values:
        return [], []

    order = sorted(range(len(values)), key=lambda i: values[i])
    assignment = [0] * len(values)

    groups: list[list[float]] = [[values[order[0]]]]
    assignment[order[0]] = 0

    for i in order[1:]:
        value = values[i]
        current = groups[-1]
        mean = sum(current) / len(current)
        if value - mean > tolerance:
            groups.append([value])
        else:
            current.append(value)
        assignment[i] = len(groups) - 1

    clusters = [_scalar_cluster(members) for members in groups]
    return clusters, assignment


def _scalar_cluster(members: list[float]) -> ScalarCluster:
    mean = sum(members) / len(members)
    return ScalarCluster(
        mean=mean,
        count=len(members),
        max_delta=max(abs(m - mean) for m in members),
    )


@dataclass(frozen=True)
class PointCluster:
    centroid: tuple[float, ...]
    count: int
    max_delta: float


def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    squared = 0.0
    for x, y in zip(a, b, strict=True):
        squared += (x - y) ** 2
    return math.sqrt(squared)


def _blend(
    centroid: tuple[float, ...], weight: int, point: tuple[float, ...], count: int
) -> tuple[float, ...]:
    total = weight + count
    return tuple((c * weight + p * count) / total for c, p in zip(centroid, point, strict=True))


def cluster_points(
    points: Sequence[tuple[float, ...]], tolerance: float
) -> tuple[list[PointCluster], list[int]]:
    """Greedy nearest-centroid clustering over Euclidean distance, for points
    of any fixed dimension (2-D for shape width/height, 3-D for sRGB colors).

    Distinct points are visited in (descending frequency, ascending value)
    order, since the greedy assignment depends on visit order and this makes
    it deterministic rather than dependent on input order. Each point is
    assigned to the nearest existing centroid within `tolerance`, or starts a
    new cluster; centroids are a running weighted average, so the result is
    not globally optimal — `max_delta` on the outcome is what exposes that.

    Returns `(clusters, assignment)` where `assignment[i]` indexes into
    `clusters` for `points[i]`.
    """
    if not points:
        return [], []

    frequency = Counter(points)
    distinct = sorted(frequency, key=lambda p: (-frequency[p], p))

    centroids: list[tuple[float, ...]] = []
    weights: list[int] = []
    cluster_of: dict[tuple[float, ...], int] = {}

    for point in distinct:
        count = frequency[point]
        best_index, _ = _nearest_centroid(point, centroids, tolerance)

        if best_index is None:
            centroids.append(point)
            weights.append(count)
            cluster_of[point] = len(centroids) - 1
        else:
            centroids[best_index] = _blend(centroids[best_index], weights[best_index], point, count)
            weights[best_index] += count
            cluster_of[point] = best_index

    # Centroids move as later points are absorbed, so a member's distance at
    # assignment time can understate its distance to the *final* centroid.
    # Recompute max_delta in a final pass against where each cluster ended up.
    farthest = [0.0] * len(centroids)
    for point in distinct:
        index = cluster_of[point]
        distance = _distance(point, centroids[index])
        if distance > farthest[index]:
            farthest[index] = distance

    assignment = [cluster_of[p] for p in points]
    clusters = [
        PointCluster(centroid=centroids[i], count=weights[i], max_delta=farthest[i])
        for i in range(len(centroids))
    ]
    return clusters, assignment


def _nearest_centroid(
    point: tuple[float, ...], centroids: list[tuple[float, ...]], tolerance: float
) -> tuple[int | None, float | None]:
    best_index: int | None = None
    best_distance: float | None = None
    for index, centroid in enumerate(centroids):
        distance = _distance(point, centroid)
        if distance <= tolerance and (best_distance is None or distance < best_distance):
            best_index, best_distance = index, distance
    return best_index, best_distance
