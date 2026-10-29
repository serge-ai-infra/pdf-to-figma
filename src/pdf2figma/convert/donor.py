"""Crop a page's SVG conversion down to one region's geometry.

Pure string/XML transform — `(page_svg, bbox) -> svg`, no I/O, tested with
hand-built SVG fixtures the same way `tests/fixtures/synthetic.py` hand-builds
PDFs. `poppler.py` is the only module in this package that touches a process;
this one only ever sees strings already in memory.

Verified against a real document (`docs/specs/s3.5-geometry-donor/spec.md`):
cairo draws every piece of actual page geometry as a top-level `<path>`
(0 native `<rect>`/`<circle>`/etc. observed) and every text glyph as a
`<use>` nested one level inside a `<g>` — so "keep a subtree iff it contains
a surviving `<path>`, drop every `<use>` unconditionally" is enough to
separate geometry from text without needing to special-case either.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from pdf2figma.convert.poppler import ConvertError
from pdf2figma.ir import BBox

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
_TAG = f"{{{SVG_NS}}}"

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

_NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
_FUNC_RE = re.compile(r"(matrix|translate|scale)\s*\(([^)]*)\)")
_URL_REF_RE = re.compile(r"url\(#([^)]+)\)")
_COORD_PAIR_RE = re.compile(rf"({_NUM})[,\s]+({_NUM})")


def _mat_mul(m1: Matrix, m2: Matrix) -> Matrix:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _parse_transform(value: str | None) -> Matrix:
    """`matrix()`, `translate()`, `scale()` only — enough for what cairo
    emits. `rotate()`/`skew*()` fall back to identity rather than a wrong
    guess; no case to test them against yet (same stance S1 already took on
    rotated content generally — out of scope, not silently approximated)."""
    if not value:
        return IDENTITY

    result = IDENTITY
    for name, args in _FUNC_RE.findall(value):
        numbers = [float(n) for n in re.findall(_NUM, args)]
        if name == "matrix" and len(numbers) == 6:
            m: Matrix = tuple(numbers)  # type: ignore[assignment]
        elif name == "translate":
            tx = numbers[0] if numbers else 0.0
            ty = numbers[1] if len(numbers) > 1 else 0.0
            m = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif name == "scale":
            sx = numbers[0] if numbers else 1.0
            sy = numbers[1] if len(numbers) > 1 else sx
            m = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        else:
            continue
        result = _mat_mul(result, m)
    return result


def _apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def _path_bbox(d: str, m: Matrix) -> tuple[float, float, float, float] | None:
    """Cairo emits only absolute `M`/`L`/`C`/`Z` with plain numeric
    coordinate pairs (verified: no relative commands, no flags to
    misparse) — scanning coordinate pairs after stripping command letters
    is exact for this output, not a heuristic. Only actual path-command
    letters are stripped, not every letter — `_NUM` allows an exponent
    (`1e-05`), and stripping a bare `e`/`E` would corrupt one number into
    two before `_COORD_PAIR_RE` ever sees it."""
    stripped = re.sub(r"[MLHVCSQTAZmlhvcsqtaz]", " ", d)
    pairs = _COORD_PAIR_RE.findall(stripped)
    if not pairs:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for sx, sy in pairs:
        x, y = _apply(m, float(sx), float(sy))
        xs.append(x)
        ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _intersects(box: tuple[float, float, float, float], bbox: BBox) -> bool:
    x0, y0, x1, y1 = box
    return not (x1 < bbox.x or x0 > bbox.right or y1 < bbox.y or y0 > bbox.bottom)


def _prune(el: ET.Element, inherited: Matrix, bbox: BBox) -> bool:
    """Depth-first: drop every `<use>` outright; keep a `<path>` iff its
    absolute bbox intersects the target; keep a container iff at least one
    child survives. Returns whether `el` itself survived. Mutates `el` in
    place, removing dropped children — original attributes of anything kept
    are untouched, so inherited fill/transform on a surviving ancestor
    `<g>` stays correct without re-deriving the SVG cascade by hand."""
    tag = el.tag.removeprefix(_TAG)
    here = _mat_mul(inherited, _parse_transform(el.get("transform")))

    if tag == "use":
        return False

    if tag == "path":
        d = el.get("d")
        box = _path_bbox(d, here) if d else None
        return box is not None and _intersects(box, bbox)

    survivors = [child for child in list(el) if _prune(child, here, bbox)]
    for child in list(el):
        if child not in survivors:
            el.remove(child)
    return bool(survivors)


def _referenced_ids(el: ET.Element) -> set[str]:
    """Every id this element (not its subtree) points at, via `url(#id)` in
    any attribute value or an `xlink:href`/`href` anchor — recurses into
    children so a kept container reports everything its descendants need."""
    ids: set[str] = set()
    for value in el.attrib.values():
        ids.update(_URL_REF_RE.findall(value))
    href = el.get(f"{{{XLINK_NS}}}href") or el.get("href")
    if href and href.startswith("#"):
        ids.add(href[1:])
    for child in el:
        ids |= _referenced_ids(child)
    return ids


def crop_to_donor(page_svg: str, bbox: BBox) -> str:
    """Filter `page_svg` down to the geometry inside `bbox` (page-space
    points, same units the SVG's own `viewBox` already uses) and rewrite the
    viewport to it. See module docstring for what "geometry" excludes."""
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    try:
        root = ET.fromstring(page_svg)
    except ET.ParseError as exc:
        raise ConvertError(f"page SVG is not well-formed: {exc}") from exc

    defs = root.find(f"{_TAG}defs")
    body = [child for child in root if child is not defs]

    kept_body = [child for child in body if _prune(child, IDENTITY, bbox)]

    if defs is not None:
        # Referenced by what actually survived, not by the whole original
        # tree — a dropped sibling's `url(#...)` must not keep a defs entry
        # alive for content that no longer exists in the output.
        referenced: set[str] = set()
        for kept in kept_body:
            referenced |= _referenced_ids(kept)
        # Fixed point for defs-referencing-defs (e.g. a clipPath whose own
        # fill references a gradient) — not exercised by the one document
        # this was verified against (see spec's Risks), cheap enough to
        # handle anyway rather than silently drop a chained reference.
        changed = True
        while changed:
            changed = False
            for entry in defs:
                entry_id = entry.get("id")
                if entry_id in referenced:
                    for further in _referenced_ids(entry):
                        if further not in referenced:
                            referenced.add(further)
                            changed = True

        for entry in list(defs):
            entry_id = entry.get("id")
            if entry_id is None or entry_id not in referenced:
                defs.remove(entry)

    for child in list(root):
        root.remove(child)
    if defs is not None and len(defs) > 0:
        root.append(defs)
    for child in kept_body:
        root.append(child)

    root.set("width", f"{bbox.w}pt")
    root.set("height", f"{bbox.h}pt")
    root.set("viewBox", f"{bbox.x} {bbox.y} {bbox.w} {bbox.h}")

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
