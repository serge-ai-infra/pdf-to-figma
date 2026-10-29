"""PDF extraction via pdfplumber.

pdfplumber reports characters, not runs, and already in top-left coordinates —
which is the convention the IR wants, so no flipping is needed. Grouping
characters into runs is *our* inference and the main place this module can be
wrong, so the rules are explicit and parameterized rather than tuned in silence.
"""

from __future__ import annotations

import io
from collections.abc import Iterator, Sequence
from typing import Any

import pdfplumber

from pdf2figma.extract.base import ExtractError, ExtractInput, ExtractOptions
from pdf2figma.ir import (
    BBox,
    Color,
    Document,
    Font,
    ImageNode,
    Node,
    Page,
    ShapeKind,
    ShapeNode,
    SourceInfo,
    Stroke,
    TextNode,
)

_PDF_MAGIC = b"%PDF-"

# A curve whose box is this close to square, and which is built from enough
# points to be a closed round shape, is called an ellipse. Anything else stays a
# path: later stages cluster on these labels, so a wrong ellipse contaminates a
# whole component candidate, while a vague path merely delays the decision.
_ELLIPSE_ASPECT_TOLERANCE = 0.06
_ELLIPSE_MIN_POINTS = 8

# A rounded-rect card can have a near-square box and plenty of points too — its
# corner arcs alone clear _ELLIPSE_MIN_POINTS — so square-ish-and-many-points
# isn't sufficient. What it lacks is roundness: pdfplumber's `pts` for a curve
# are its path vertices, and a rounded rect's straight edges sit *outside* the
# ellipse inscribed in the same box (a true ellipse point normalizes to
# radius 1 from the box center; measured on a real card here, the far corners
# of the straight edges came out to ~1.68 against a real small circle's ~1.11).
# The tolerance sits between those two measured values.
_ELLIPSE_RADIAL_TOLERANCE = 1.3

_BOLD_MARKERS = ("bold", "black", "heavy", "semibold", "demibold")
_ITALIC_MARKERS = ("italic", "oblique")

# PostScript composite names bolt the style onto the family with a hyphen —
# "Helvetica-Bold", "Times-BoldItalic" — which is exactly the form Figma's
# loadFontAsync rejects: it wants family "Helvetica" + style "Bold", not a
# family literally named "Helvetica-Bold". Stripping a *known* style suffix
# (never an arbitrary hyphenated segment, so a genuine hyphenated family name
# survives) turns every Standard-14 font PDF actually uses into a family
# Figma/macOS already has installed, no font extraction required.
_STYLE_SUFFIXES = {
    "regular",
    "roman",
    "bold",
    "italic",
    "oblique",
    "bolditalic",
    "boldoblique",
}


def _strip_style_suffix(family: str) -> str:
    base, sep, suffix = family.rpartition("-")
    if sep and base and suffix.lower() in _STYLE_SUFFIXES:
        return base
    return family


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _to_hex(components: Sequence[float]) -> str | None:
    """Normalize a PDF color operand to sRGB hex.

    PDF hands over gray, RGB or CMYK depending on the color space in force.
    CMYK is converted with the naive formula — good enough to cluster on, and the
    document records that the source was not sRGB so nobody mistakes it for exact.
    """
    values = [float(c) for c in components]

    if len(values) == 1:
        gray = _clamp01(values[0])
        rgb = (gray, gray, gray)
    elif len(values) == 3:
        rgb = (_clamp01(values[0]), _clamp01(values[1]), _clamp01(values[2]))
    elif len(values) == 4:
        c, m, y, k = (_clamp01(v) for v in values)
        rgb = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    else:
        return None

    return "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb)


def _color_of(raw: Any) -> Color | None:
    if raw is None:
        return None
    components = raw if isinstance(raw, (list, tuple)) else (raw,)
    if not components:
        return None
    try:
        hex_value = _to_hex(components)
    except (TypeError, ValueError):
        return None
    return Color(hex=hex_value) if hex_value else None


def _font_of(char: dict[str, Any]) -> Font:
    raw_name = str(char.get("fontname") or "unknown")
    # Subset prefixes look like "ABCDEF+Helvetica-Bold" and say nothing useful.
    subset_stripped = raw_name.split("+", 1)[-1]
    lowered = subset_stripped.lower()
    size = float(char.get("size") or 0.0)

    return Font(
        family=_strip_style_suffix(subset_stripped),
        size=size if size > 0 else 1.0,
        weight=700 if any(marker in lowered for marker in _BOLD_MARKERS) else None,
        italic=any(marker in lowered for marker in _ITALIC_MARKERS),
    )


def _same_run(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Whether two adjacent characters belong to the same styled run."""
    return (
        a["fontname"] == b["fontname"]
        and abs(float(a["size"]) - float(b["size"])) < 0.01
        and a.get("non_stroking_color") == b.get("non_stroking_color")
        and abs(float(a["top"]) - float(b["top"])) < 0.01 * max(float(a["size"]), 1.0) + 0.5
    )


def _group_runs(
    chars: list[dict[str, Any]], gap_ratio: float
) -> Iterator[list[dict[str, Any]]]:
    """Group characters into runs by line, style and horizontal spacing."""
    if not chars:
        return

    ordered = sorted(chars, key=lambda c: (round(float(c["top"]), 1), float(c["x0"])))
    run = [ordered[0]]

    for char in ordered[1:]:
        previous = run[-1]
        gap = float(char["x0"]) - float(previous["x1"])
        limit = gap_ratio * max(float(char.get("size") or 1.0), 1.0)

        if _same_run(previous, char) and -limit <= gap <= limit:
            run.append(char)
        else:
            yield run
            run = [char]

    yield run


def _run_to_node(run: list[dict[str, Any]], node_id: str, z: int, want_color: bool) -> TextNode:
    text = "".join(str(c.get("text") or "") for c in run)
    x0 = min(float(c["x0"]) for c in run)
    x1 = max(float(c["x1"]) for c in run)
    top = min(float(c["top"]) for c in run)
    bottom = max(float(c["bottom"]) for c in run)

    color = _color_of(run[0].get("non_stroking_color")) if want_color else None

    return TextNode(
        id=node_id,
        bbox=BBox(x=x0, y=top, w=x1 - x0, h=bottom - top),
        z=z,
        text=text,
        font=_font_of(run[0]),
        color=color,
        # pdfplumber reports the fill in force for each character, so this is the
        # document's own value rather than something inferred from paint order.
        color_confidence="exact" if color is not None else "unknown",
    )


def _bbox_of(obj: dict[str, Any]) -> BBox:
    x0, x1 = float(obj["x0"]), float(obj["x1"])
    top, bottom = float(obj["top"]), float(obj["bottom"])
    return BBox(x=min(x0, x1), y=min(top, bottom), w=abs(x1 - x0), h=abs(bottom - top))


def _hugs_ellipse(points: Sequence[tuple[float, float]], box: BBox) -> bool:
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    rx, ry = box.w / 2, box.h / 2
    return all(
        ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= _ELLIPSE_RADIAL_TOLERANCE
        for x, y in points
    )


def _classify_curve(obj: dict[str, Any], box: BBox) -> ShapeKind:
    points = obj.get("pts") or []
    if box.w <= 0 or box.h <= 0:
        return "path"
    aspect = box.w / box.h
    near_square = abs(aspect - 1.0) <= _ELLIPSE_ASPECT_TOLERANCE
    if near_square and len(points) >= _ELLIPSE_MIN_POINTS and _hugs_ellipse(points, box):
        return "ellipse"
    return "path"


def _shape_node(obj: dict[str, Any], kind: ShapeKind, node_id: str, z: int) -> ShapeNode:
    fill = _color_of(obj.get("non_stroking_color")) if obj.get("fill") else None
    stroke_color = _color_of(obj.get("stroking_color")) if obj.get("stroke") else None
    stroke = (
        Stroke(color=stroke_color, width=float(obj.get("linewidth") or 0.0))
        if stroke_color is not None
        else None
    )

    return ShapeNode(
        id=node_id,
        bbox=_bbox_of(obj),
        z=z,
        shape=kind,
        fill=fill,
        stroke=stroke,
        closed=bool(obj.get("fill")) or kind in {"rect", "ellipse"},
    )


class PdfExtractor:
    """Extractor over pdfplumber. Takes bytes; never touches the filesystem."""

    name = "pdfplumber"

    def supports(self, inp: ExtractInput) -> bool:
        return inp.data[:5] == _PDF_MAGIC

    def extract(self, inp: ExtractInput, opts: ExtractOptions) -> Document:
        if not self.supports(inp):
            raise ExtractError("Not a PDF: the file does not begin with %PDF-.")

        try:
            with pdfplumber.open(io.BytesIO(inp.data)) as pdf:
                return self._extract_open(pdf, opts)
        except ExtractError:
            raise
        except Exception as exc:  # pdfminer raises a wide variety of types
            raise ExtractError(f"Could not read the PDF: {exc}") from exc

    def _extract_open(self, pdf: Any, opts: ExtractOptions) -> Document:
        metadata = pdf.metadata or {}
        wanted = set(opts.pages) if opts.pages is not None else None

        pages: list[Page] = []
        for index, page in enumerate(pdf.pages):
            if wanted is not None and index not in wanted:
                continue
            pages.append(self._extract_page(page, index, opts))

        return Document(
            source=SourceInfo(
                page_count=len(pdf.pages),
                producer=_clean(metadata.get("Producer")),
                creator=_clean(metadata.get("Creator")),
                title=_clean(metadata.get("Title")),
            ),
            pages=pages,
        )

    def _extract_page(self, page: Any, index: int, opts: ExtractOptions) -> Page:
        nodes: list[Node] = []

        # Painting order is approximated as shapes, then images, then text. PDF
        # content streams do carry the real order, but pdfplumber groups objects
        # by type and does not preserve it. The approximation matches how these
        # documents are actually drawn — background, then artwork, then labels —
        # and z is only used for tie-breaking, never for correctness.
        z = 0

        for obj in page.rects:
            nodes.append(_shape_node(obj, "rect", f"p{index}.r{z}", z))
            z += 1

        for obj in page.lines:
            nodes.append(_shape_node(obj, "line", f"p{index}.l{z}", z))
            z += 1

        for obj in page.curves:
            box = _bbox_of(obj)
            nodes.append(_shape_node(obj, _classify_curve(obj, box), f"p{index}.c{z}", z))
            z += 1

        for obj in page.images:
            nodes.append(
                ImageNode(
                    id=f"p{index}.i{z}",
                    bbox=_bbox_of(obj),
                    z=z,
                    image_id=str(obj.get("name") or f"image-{z}"),
                )
            )
            z += 1

        chars = list(page.chars)
        if any(not c.get("upright", True) for c in chars):
            opts.warnings.append(
                f"page {index + 1}: rotated text present; bounding boxes are axis-aligned "
                "approximations and rotation is not recorded (out of scope for IR 0.1)"
            )

        for run in _group_runs(chars, opts.run_gap_ratio):
            if not any(str(c.get("text") or "").strip() for c in run):
                continue
            nodes.append(_run_to_node(run, f"p{index}.t{z}", z, opts.text_color))
            z += 1

        return Page(
            index=index,
            width=float(page.width),
            height=float(page.height),
            rotation=int(page.rotation or 0),
            nodes=nodes,
        )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
