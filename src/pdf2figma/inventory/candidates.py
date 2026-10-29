"""Atom candidates — recurring shapes and recurring text styles.

Grouped across the whole corpus, reusing the palette's color clusters and the
type scale's size clusters (`tokens.py`) so a candidate's reported style never
disagrees with the tokens the rest of the report describes. A group becomes a
candidate only once it recurs `min_occurrences` times; anything rarer is
architecture.md's "instance, deliberately not generalized" and is only ever
counted, in `unclustered_shapes` / `unclustered_text` — never reported as a
spurious one-member candidate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pdf2figma.inventory.cluster import cluster_points, cluster_scalars
from pdf2figma.inventory.model import Occurrence, ShapeCandidate, TextCandidate
from pdf2figma.inventory.tokens import PaletteResult, TypeScaleResult
from pdf2figma.ir import Document, ShapeKind, ShapeNode, TextNode

_OCCURRENCE_SAMPLE_CAP = 20
"""Occurrences beyond this are still counted in `count`, never silently dropped."""

_SAMPLE_TEXT_CAP = 10


def _presence_ratio(occurrences: list[Occurrence], total_documents: int) -> float:
    if total_documents <= 0:
        return 0.0
    return len({occ.document for occ in occurrences}) / total_documents


@dataclass
class _ShapeInstance:
    width: float
    height: float
    stroke_width: float | None
    occurrence: Occurrence


def build_shape_candidates(
    documents: Sequence[Document],
    palette: PaletteResult,
    size_tolerance: float,
    min_occurrences: int,
) -> tuple[list[ShapeCandidate], int]:
    """Bucket by exact shape kind, then by (fill, stroke, stroke-width) cluster,
    then cluster (width, height) within each bucket. A bucket's geometry
    cluster becomes a candidate once it recurs `min_occurrences` times.
    """
    stroke_widths = [
        node.stroke.width
        for document in documents
        for page in document.pages
        for node in page.nodes
        if isinstance(node, ShapeNode) and node.stroke is not None
    ]
    _, stroke_width_assignment = cluster_scalars(stroke_widths, size_tolerance)
    stroke_width_of: dict[float, int] = dict(
        zip(stroke_widths, stroke_width_assignment, strict=True)
    )

    by_key: dict[tuple[ShapeKind, int | None, int | None, int | None], list[_ShapeInstance]] = {}

    for doc_index, document in enumerate(documents):
        for page_index, page in enumerate(document.pages):
            for node in page.nodes:
                if not isinstance(node, ShapeNode):
                    continue
                fill_cluster = palette.cluster_of.get(node.fill.hex) if node.fill else None
                stroke_cluster = (
                    palette.cluster_of.get(node.stroke.color.hex) if node.stroke else None
                )
                stroke_width_bucket = (
                    stroke_width_of.get(node.stroke.width) if node.stroke else None
                )
                key = (node.shape, fill_cluster, stroke_cluster, stroke_width_bucket)
                by_key.setdefault(key, []).append(
                    _ShapeInstance(
                        width=node.bbox.w,
                        height=node.bbox.h,
                        stroke_width=node.stroke.width if node.stroke else None,
                        occurrence=Occurrence(document=doc_index, page=page_index, node_id=node.id),
                    )
                )

    candidates: list[ShapeCandidate] = []
    unclustered = 0
    next_id = 0

    for (shape, fill_cluster, stroke_cluster, stroke_width_bucket), instances in sorted(
        by_key.items(), key=lambda item: str(item[0])
    ):
        points = [(inst.width, inst.height) for inst in instances]
        geometry_clusters, assignment = cluster_points(points, size_tolerance)

        groups: dict[int, list[_ShapeInstance]] = {}
        for inst, local_index in zip(instances, assignment, strict=True):
            groups.setdefault(local_index, []).append(inst)

        for local_index, members in sorted(groups.items()):
            if len(members) < min_occurrences:
                unclustered += len(members)
                continue

            geometry = geometry_clusters[local_index]
            occurrences = [m.occurrence for m in members]
            stroke_width_mean = (
                sum(m.stroke_width for m in members if m.stroke_width is not None) / len(members)
                if stroke_width_bucket is not None
                else None
            )

            candidates.append(
                ShapeCandidate(
                    id=f"shape-{next_id}",
                    shape=shape,
                    fill=palette.tokens[fill_cluster].hex if fill_cluster is not None else None,
                    stroke_color=(
                        palette.tokens[stroke_cluster].hex if stroke_cluster is not None else None
                    ),
                    stroke_width=stroke_width_mean,
                    width=geometry.centroid[0],
                    height=geometry.centroid[1],
                    count=len(members),
                    documents=len({m.occurrence.document for m in members}),
                    presence_ratio=_presence_ratio(occurrences, len(documents)),
                    variant=_presence_ratio(occurrences, len(documents)) < 1.0,
                    max_size_delta=geometry.max_delta,
                    occurrences=occurrences[:_OCCURRENCE_SAMPLE_CAP],
                )
            )
            next_id += 1

    return candidates, unclustered


@dataclass
class _TextInstance:
    text: str
    occurrence: Occurrence


def build_text_candidates(
    documents: Sequence[Document],
    palette: PaletteResult,
    type_scale: TypeScaleResult,
    min_occurrences: int,
) -> tuple[list[TextCandidate], int]:
    """Key on style only — family, weight, italic, size cluster, color cluster.

    Text content is expected to vary within a matching style: that's a future
    property/variable slot, not noise, so content is reported as a capped
    sample rather than clustered on.
    """
    by_key: dict[tuple[str, int | None, bool, int, int | None], list[_TextInstance]] = {}

    for doc_index, document in enumerate(documents):
        for page_index, page in enumerate(document.pages):
            for node in page.nodes:
                if not isinstance(node, TextNode):
                    continue
                size_key = (node.font.family, node.font.weight, node.font.italic, node.font.size)
                size_cluster = type_scale.cluster_of.get(size_key)
                if size_cluster is None:
                    continue  # every observed size was clustered when the type scale was built
                color_cluster = palette.cluster_of.get(node.color.hex) if node.color else None
                font = node.font

                key = (font.family, font.weight, font.italic, size_cluster, color_cluster)
                by_key.setdefault(key, []).append(
                    _TextInstance(
                        text=node.text,
                        occurrence=Occurrence(document=doc_index, page=page_index, node_id=node.id),
                    )
                )

    candidates: list[TextCandidate] = []
    unclustered = 0
    next_id = 0

    for (family, weight, italic, size_cluster, color_cluster), members in sorted(
        by_key.items(), key=lambda item: str(item[0])
    ):
        if len(members) < min_occurrences:
            unclustered += len(members)
            continue

        occurrences = [m.occurrence for m in members]
        sample_texts = sorted({m.text for m in members})[:_SAMPLE_TEXT_CAP]

        candidates.append(
            TextCandidate(
                id=f"text-{next_id}",
                family=family,
                weight=weight,
                italic=italic,
                size=type_scale.tokens[size_cluster].size,
                color=palette.tokens[color_cluster].hex if color_cluster is not None else None,
                count=len(members),
                documents=len({m.occurrence.document for m in members}),
                presence_ratio=_presence_ratio(occurrences, len(documents)),
                variant=_presence_ratio(occurrences, len(documents)) < 1.0,
                sample_texts=sample_texts,
                occurrences=occurrences[:_OCCURRENCE_SAMPLE_CAP],
            )
        )
        next_id += 1

    return candidates, unclustered
