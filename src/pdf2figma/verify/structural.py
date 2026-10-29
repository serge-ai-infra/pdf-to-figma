"""Exact, per-node comparison of source IR against what actually got built.

Deliberately dumb, same spirit as the IR itself: no judgment about whether a
`missing` region is a bug or an intended skip — that's the (deferred) repair
loop's job. This only reports what differs, in the "X, expected Y" form
`architecture.md` itself uses as the example of what structural diff is for.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pdf2figma.ir import BBox, Node, ShapeNode, TextNode
from pdf2figma.verify.model import (
    BuiltDocument,
    BuiltNode,
    RegionStatus,
    StructuralCounts,
    StructuralRegion,
    StructuralReport,
    StructuralTolerances,
)

# Font size and stroke width are compared in points, the same unit as bbox.
# The tolerance only absorbs float round-trips through Figma, not real drift.
_SIZE_TOLERANCE_PT = 0.05


def _bbox_delta(a: BBox, b: BBox) -> float:
    return max(abs(a.x - b.x), abs(a.y - b.y), abs(a.w - b.w), abs(a.h - b.h))


def _style_notes(source: Node, built_fill: str | None, built_stroke: str | None) -> list[str]:
    notes: list[str] = []

    if isinstance(source, TextNode):
        expected_fill = source.color.hex if source.color else None
        if built_fill != expected_fill:
            notes.append(f"fill {built_fill!r}, expected {expected_fill!r}")
    elif isinstance(source, ShapeNode):
        expected_fill = source.fill.hex if source.fill else None
        if built_fill != expected_fill:
            notes.append(f"fill {built_fill!r}, expected {expected_fill!r}")
        expected_stroke = source.stroke.color.hex if source.stroke else None
        if built_stroke != expected_stroke:
            notes.append(f"stroke {built_stroke!r}, expected {expected_stroke!r}")
    # ImageNode: fill/stroke aren't comparable concepts; nothing to check here.

    return notes


def _size_notes(source: Node, built: BuiltNode) -> list[str]:
    """Font size and stroke width, in points. Skipped when the built side can't say."""
    if isinstance(source, TextNode) and built.font is not None:
        if abs(built.font.size - source.font.size) <= _SIZE_TOLERANCE_PT:
            return []
        return [f"font size {built.font.size:g}pt, expected {source.font.size:g}pt"]
    if isinstance(source, ShapeNode) and source.stroke and built.stroke_width is not None:
        if abs(built.stroke_width - source.stroke.width) <= _SIZE_TOLERANCE_PT:
            return []
        return [f"stroke width {built.stroke_width:g}pt, expected {source.stroke.width:g}pt"]
    return []


def payload_notes_for(payload_data: Mapping[str, object], node_id: str) -> list[str]:
    """Best-effort context for a `missing` region, from the emitter's own payload.

    Only `unsupportedReason` (path/image, recorded at emit time) is a real
    explanation. Anything else is just what the payload knew going in — a
    `missing` node with no `unsupportedReason` most often means a build-time
    font failure, which the payload can't record because it happens later.
    """
    nodes = payload_data.get("nodes")
    if not isinstance(nodes, list):
        return []

    for entry in nodes:
        if not isinstance(entry, dict) or entry.get("id") != node_id:
            continue

        reason = entry.get("unsupportedReason")
        if reason:
            return [f"payload: {reason}"]

        bits = [f"kind={entry.get('kind')}"]
        font = entry.get("font")
        if isinstance(font, dict) and font.get("family"):
            bits.append(f"font={font['family']}")
        if entry.get("candidateId"):
            bits.append(f"candidateId={entry['candidateId']}")

        return [
            f"payload: {', '.join(bits)} — no unsupportedReason recorded, "
            "likely a build-time skip (e.g. an unloadable font)"
        ]

    return []


def diff_structural(
    source_nodes: Sequence[Node],
    built: BuiltDocument,
    tolerances: StructuralTolerances,
    payload_data: Mapping[str, object] | None = None,
) -> StructuralReport:
    built_by_id = {node.id: node for node in built.nodes}
    seen_built_ids: set[str] = set()
    regions: list[StructuralRegion] = []

    for source in source_nodes:
        built_node = built_by_id.get(source.id)

        if built_node is None:
            notes = payload_notes_for(payload_data, source.id) if payload_data else []
            regions.append(StructuralRegion(id=source.id, status="missing", notes=notes))
            continue

        seen_built_ids.add(source.id)
        bbox_delta = _bbox_delta(source.bbox, built_node.bbox)
        notes = _style_notes(source, built_node.fill, built_node.stroke_color)

        if isinstance(source, TextNode) and built_node.text != source.text:
            notes.append(f"text {built_node.text!r}, expected {source.text!r}")
        notes.extend(_size_notes(source, built_node))
        if bbox_delta > tolerances.bbox:
            notes.append(f"bbox delta {bbox_delta:.2f}pt, expected within {tolerances.bbox}pt")

        status: RegionStatus = "mismatched" if notes else "matched"
        regions.append(
            StructuralRegion(id=source.id, status=status, bbox_delta=bbox_delta, notes=notes)
        )

    for built_id in built_by_id:
        if built_id not in seen_built_ids:
            regions.append(StructuralRegion(id=built_id, status="extra"))

    counts = StructuralCounts(
        matched=sum(1 for r in regions if r.status == "matched"),
        mismatched=sum(1 for r in regions if r.status == "mismatched"),
        missing=sum(1 for r in regions if r.status == "missing"),
        extra=sum(1 for r in regions if r.status == "extra"),
    )
    return StructuralReport(tolerances=tolerances, counts=counts, regions=regions)
