"""Palette, type scale and spacing — the three token kinds this stage reports.

`build_palette` and `build_type_scale` each return, alongside the tokens
themselves, the lookup a caller needs to place *any* color or font size seen
in the corpus into the same clusters — that lookup is what `candidates.py`
reuses, so a shape's fill and a palette entry never disagree about which
colors are "the same." The clustering itself happens exactly once per token
kind, here; nothing downstream re-clusters.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pdf2figma.inventory.cluster import cluster_points, cluster_scalars
from pdf2figma.inventory.model import ColorToken, Role, SizeToken, SpacingToken
from pdf2figma.ir import Document, Node, ShapeNode, TextNode

SizeKey = tuple[str, int | None, bool, float]
"""(family, weight, italic, exact size) — identical tuples always co-cluster."""


def hex_to_rgb(hex_value: str) -> tuple[float, float, float]:
    return (
        float(int(hex_value[1:3], 16)),
        float(int(hex_value[3:5], 16)),
        float(int(hex_value[5:7], 16)),
    )


def rgb_to_hex(rgb: tuple[float, ...]) -> str:
    channels = (min(255, max(0, round(c))) for c in rgb)
    return "#" + "".join(f"{c:02x}" for c in channels)


@dataclass(frozen=True)
class PaletteResult:
    tokens: list[ColorToken]
    cluster_of: dict[str, int] = field(default_factory=dict)
    """hex -> index into `tokens`. Exact-match lookup: identical hex strings are
    identical points, and identical points always land in the same cluster."""


def build_palette(documents: Sequence[Document], tolerance: float) -> PaletteResult:
    """Cluster every color used as a text color, shape fill, or shape stroke.

    One pass, one clustering call — the result this returns is the only
    authority on "which colors are the same" for the rest of this stage.
    """
    hexes: list[str] = []
    roles: list[Role] = []

    for document in documents:
        for page in document.pages:
            for node in page.nodes:
                if isinstance(node, TextNode) and node.color is not None:
                    hexes.append(node.color.hex)
                    roles.append("text")
                elif isinstance(node, ShapeNode):
                    if node.fill is not None:
                        hexes.append(node.fill.hex)
                        roles.append("fill")
                    if node.stroke is not None:
                        hexes.append(node.stroke.color.hex)
                        roles.append("stroke")

    points = [hex_to_rgb(h) for h in hexes]
    clusters, assignment = cluster_points(points, tolerance)
    if not clusters:
        return PaletteResult(tokens=[])

    role_counts: list[dict[Role, int]] = [{} for _ in clusters]
    raw_cluster_of: dict[str, int] = {}
    for hex_value, role, cluster_index in zip(hexes, roles, assignment, strict=True):
        raw_cluster_of[hex_value] = cluster_index
        role_counts[cluster_index][role] = role_counts[cluster_index].get(role, 0) + 1

    representative = [rgb_to_hex(c.centroid) for c in clusters]
    order = sorted(range(len(clusters)), key=lambda i: (-clusters[i].count, representative[i]))
    remap = {old: new for new, old in enumerate(order)}

    tokens = [
        ColorToken(
            hex=representative[old],
            count=clusters[old].count,
            max_delta=clusters[old].max_delta,
            roles=role_counts[old],
        )
        for old in order
    ]
    cluster_of = {hex_value: remap[old] for hex_value, old in raw_cluster_of.items()}
    return PaletteResult(tokens=tokens, cluster_of=cluster_of)


@dataclass(frozen=True)
class TypeScaleResult:
    tokens: list[SizeToken]
    cluster_of: dict[SizeKey, int] = field(default_factory=dict)
    """(family, weight, italic, exact size) -> index into `tokens`."""


def build_type_scale(documents: Sequence[Document], tolerance: float) -> TypeScaleResult:
    """Cluster font sizes within each exact (family, weight, italic) group.

    Different families are never the same token regardless of size, so
    grouping is exact there and clustering only applies to the size itself.
    """
    groups: dict[tuple[str, int | None, bool], list[float]] = {}
    for document in documents:
        for page in document.pages:
            for node in page.nodes:
                if isinstance(node, TextNode):
                    key = (node.font.family, node.font.weight, node.font.italic)
                    groups.setdefault(key, []).append(node.font.size)

    tokens: list[SizeToken] = []
    cluster_of: dict[SizeKey, int] = {}

    for family, weight, italic in sorted(groups, key=lambda k: (k[0], k[1] or 0, k[2])):
        sizes = groups[(family, weight, italic)]
        clusters, assignment = cluster_scalars(sizes, tolerance)

        offset = len(tokens)
        for cluster in clusters:
            tokens.append(
                SizeToken(
                    family=family,
                    weight=weight,
                    italic=italic,
                    size=cluster.mean,
                    count=cluster.count,
                    max_delta=cluster.max_delta,
                )
            )
        for size, local_index in zip(sizes, assignment, strict=True):
            cluster_of[(family, weight, italic, size)] = offset + local_index

    return TypeScaleResult(tokens=tokens, cluster_of=cluster_of)


def build_spacing(documents: Sequence[Document], tolerance: float) -> list[SpacingToken]:
    """Nearest-neighbor gap in each of 4 directions for every node, per page.

    "Neighbor" means the closest other node on the same page whose bbox
    overlaps on the perpendicular axis — sort-based per page, not a full
    pairwise scan of every node against every other.
    """
    x_gaps: list[float] = []
    y_gaps: list[float] = []

    for document in documents:
        for page in document.pages:
            gx, gy = _page_gaps(page.nodes)
            x_gaps.extend(gx)
            y_gaps.extend(gy)

    return _spacing_tokens("x", x_gaps, tolerance) + _spacing_tokens("y", y_gaps, tolerance)


def _spacing_tokens(
    axis: Literal["x", "y"], values: list[float], tolerance: float
) -> list[SpacingToken]:
    clusters, _ = cluster_scalars(values, tolerance)
    return [
        SpacingToken(axis=axis, gap=cluster.mean, count=cluster.count, max_delta=cluster.max_delta)
        for cluster in sorted(clusters, key=lambda c: -c.count)
    ]


def _page_gaps(nodes: Sequence[Node]) -> tuple[list[float], list[float]]:
    boxes = [n.bbox for n in nodes]

    x_gaps: list[float] = []
    by_left = sorted(range(len(boxes)), key=lambda i: boxes[i].x)
    for rank, i in enumerate(by_left):
        box = boxes[i]
        best: float | None = None
        for j in by_left[rank + 1 :]:
            other = boxes[j]
            if other.x < box.right:
                continue
            if _overlaps(box.y, box.bottom, other.y, other.bottom):
                gap = other.x - box.right
                if best is None or gap < best:
                    best = gap
                break
        if best is not None:
            x_gaps.append(best)

    y_gaps: list[float] = []
    by_top = sorted(range(len(boxes)), key=lambda i: boxes[i].y)
    for rank, i in enumerate(by_top):
        box = boxes[i]
        best = None
        for j in by_top[rank + 1 :]:
            other = boxes[j]
            if other.y < box.bottom:
                continue
            if _overlaps(box.x, box.right, other.x, other.right):
                gap = other.y - box.bottom
                if best is None or gap < best:
                    best = gap
                break
        if best is not None:
            y_gaps.append(best)

    return x_gaps, y_gaps


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1
