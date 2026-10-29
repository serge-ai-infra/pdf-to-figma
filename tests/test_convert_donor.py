"""`crop_to_donor` against hand-built SVG strings — no real PDF, no poppler,
no I/O. Coordinates are chosen the same way `tests/fixtures/synthetic.py`
chooses PDF coordinates: written next to the assertion that checks them.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pdf2figma.convert.donor import IDENTITY, _path_bbox, crop_to_donor
from pdf2figma.ir import BBox

SVG_NS = "http://www.w3.org/2000/svg"


def _svg(body: str, defs: str = "") -> str:
    defs_block = f"<defs>{defs}</defs>" if defs else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="300pt" height="300pt" viewBox="0 0 300 300">{defs_block}{body}</svg>'
    )


def _paths(donor_svg: str) -> list[ET.Element]:
    root = ET.fromstring(donor_svg)
    return list(root.iter(f"{{{SVG_NS}}}path"))


def _uses(donor_svg: str) -> list[ET.Element]:
    root = ET.fromstring(donor_svg)
    return list(root.iter(f"{{{SVG_NS}}}use"))


class TestPathIntersection:
    def test_path_fully_inside_bbox_survives(self) -> None:
        svg = _svg('<path id="p" d="M 20 20 L 30 20 L 30 30 L 20 30 Z"/>')
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        assert [p.get("id") for p in _paths(donor)] == ["p"]

    def test_path_fully_outside_bbox_is_dropped(self) -> None:
        svg = _svg('<path id="p" d="M 200 200 L 210 200 L 210 210 L 200 210 Z"/>')
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        assert _paths(donor) == []

    def test_path_straddling_bbox_edge_survives(self) -> None:
        # Target bbox is 0,0..100,100 — this path spans 90..110, crossing the
        # right edge. Intersection, not containment: it survives whole.
        svg = _svg('<path id="p" d="M 90 50 L 110 50 L 110 60 L 90 60 Z"/>')
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        assert [p.get("id") for p in _paths(donor)] == ["p"]


class TestTransform:
    def test_matrix_transform_moves_path_into_bbox(self) -> None:
        # Raw d-coordinates (0,0)-(10,10) are nowhere near the target bbox,
        # but the matrix translates by (50, 50) — absolute position 50..60,
        # squarely inside 0,0..100,100. Bbox testing must use the
        # transformed position, not the raw d-coordinates.
        svg = _svg(
            '<path id="p" transform="matrix(1, 0, 0, 1, 50, 50)" '
            'd="M 0 0 L 10 0 L 10 10 L 0 10 Z"/>'
        )
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        assert [p.get("id") for p in _paths(donor)] == ["p"]

    def test_matrix_transform_moves_path_out_of_bbox(self) -> None:
        # Raw d-coordinates look inside the target bbox, but the matrix
        # translates them out to 500..510 — must be dropped.
        svg = _svg(
            '<path id="p" transform="matrix(1, 0, 0, 1, 500, 500)" '
            'd="M 10 10 L 20 10 L 20 20 L 10 20 Z"/>'
        )
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        assert _paths(donor) == []

    def test_transform_composes_through_a_wrapping_group(self) -> None:
        # The group carries the translate; the path itself has none. The
        # cumulative (parent * own) transform is what must be tested.
        svg = _svg(
            '<g transform="translate(50, 50)"><path id="p" d="M 0 0 L 10 0 L 10 10 L 0 10 Z"/></g>'
        )
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        assert [p.get("id") for p in _paths(donor)] == ["p"]

    def test_surviving_group_keeps_its_own_attributes_unrewritten(self) -> None:
        # A kept ancestor <g> (inherited fill, in this case) is preserved
        # verbatim, not flattened — no SVG-cascade re-derivation needed.
        svg = _svg(
            '<g fill="rgb(0%, 50%, 0%)"><path id="p" d="M 10 10 L 20 10 L 20 20 L 10 20 Z"/></g>'
        )
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        root = ET.fromstring(donor)
        group = root.find(f"{{{SVG_NS}}}g")
        assert group is not None
        assert group.get("fill") == "rgb(0%, 50%, 0%)"


class TestTextExclusion:
    def test_use_is_always_dropped_even_when_geometrically_inside_bbox(self) -> None:
        svg = _svg('<g fill="black"><use xlink:href="#glyph-0" x="10" y="10"/></g>')
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        assert _uses(donor) == []

    def test_group_left_empty_by_dropped_use_is_itself_dropped(self) -> None:
        svg = _svg('<g fill="black"><use xlink:href="#glyph-0" x="10" y="10"/></g>')
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        root = ET.fromstring(donor)
        assert list(root) == []


class TestDefs:
    def test_defs_referenced_by_a_surviving_path_is_kept(self) -> None:
        svg = _svg(
            '<path id="p" fill="url(#grad1)" d="M 10 10 L 20 10 L 20 20 L 10 20 Z"/>',
            defs='<linearGradient id="grad1"><stop offset="0"/></linearGradient>',
        )
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        root = ET.fromstring(donor)
        defs = root.find(f"{{{SVG_NS}}}defs")
        assert defs is not None
        assert [g.get("id") for g in defs] == ["grad1"]

    def test_defs_unreferenced_by_anything_kept_is_dropped_entirely(self) -> None:
        svg = _svg(
            '<path id="p" d="M 200 200 L 210 200 L 210 210 L 200 210 Z"/>',
            defs='<linearGradient id="grad1"><stop offset="0"/></linearGradient>',
        )
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        root = ET.fromstring(donor)
        assert root.find(f"{{{SVG_NS}}}defs") is None

    def test_chained_defs_reference_is_kept_via_fixed_point(self) -> None:
        # grad1 is referenced by the surviving path; grad1 itself references
        # grad-base via xlink:href (a gradient stop-sharing pattern) — both
        # must survive, not just the directly-referenced one.
        svg = _svg(
            '<path id="p" fill="url(#grad1)" d="M 10 10 L 20 10 L 20 20 L 10 20 Z"/>',
            defs=(
                '<linearGradient id="grad-base"><stop offset="0"/></linearGradient>'
                '<linearGradient id="grad1" xlink:href="#grad-base"/>'
            ),
        )
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        root = ET.fromstring(donor)
        defs = root.find(f"{{{SVG_NS}}}defs")
        assert defs is not None
        assert {g.get("id") for g in defs} == {"grad1", "grad-base"}


class TestPathBboxParsing:
    def test_scientific_notation_coordinate_is_not_split_by_command_stripping(self) -> None:
        # "1e2" is 100 — stripping *every* letter (not just path commands)
        # would turn it into "1" and "2", two bogus numbers instead of one.
        box = _path_bbox("M 1e2 1e2 L 150 100 L 150 150 L 100 150 Z", IDENTITY)
        assert box == (100.0, 100.0, 150.0, 150.0)


class TestDefsMultipleReferencesInOneAttribute:
    def test_two_url_references_in_one_style_attribute_both_survive(self) -> None:
        svg = _svg(
            '<path id="p" style="fill:url(#a);stroke:url(#b)" '
            'd="M 10 10 L 20 10 L 20 20 L 10 20 Z"/>',
            defs=(
                '<linearGradient id="a"><stop offset="0"/></linearGradient>'
                '<linearGradient id="b"><stop offset="0"/></linearGradient>'
            ),
        )
        donor = crop_to_donor(svg, BBox(x=0, y=0, w=100, h=100))
        root = ET.fromstring(donor)
        defs = root.find(f"{{{SVG_NS}}}defs")
        assert defs is not None
        assert {g.get("id") for g in defs} == {"a", "b"}


class TestViewport:
    def test_root_viewbox_and_size_are_rewritten_to_the_target_bbox(self) -> None:
        svg = _svg('<path id="p" d="M 20 20 L 30 20 L 30 30 L 20 30 Z"/>')
        donor = crop_to_donor(svg, BBox(x=18.0, y=128.0, w=188.0, h=170.0))
        root = ET.fromstring(donor)
        assert root.get("viewBox") == "18.0 128.0 188.0 170.0"
        assert root.get("width") == "188.0pt"
        assert root.get("height") == "170.0pt"
