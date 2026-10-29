"""End-to-end `pdf2figma convert donor`, via the real CLI entry point, a
real synthetic PDF and a real `pdftocairo` process.

`tests/test_convert_donor.py` covers `crop_to_donor` against hand-built SVG
strings (no PDF, no poppler); `tests/test_convert_poppler.py` covers
`page_to_svg` against a real poppler call (no crop logic). Neither runs the
two together through the CLI a user would actually type. This does — no
third-party data, no binary fixture: two small filled triangles (S1 classifies
these `path`, not `rect`/`line`/`ellipse` — confirmed below, not assumed)
plus a text run positioned to overlap one of them, so text-exclusion is
exercised against genuine geometric overlap rather than an isolated case.
"""

from __future__ import annotations

import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pdf2figma.cli import main
from pdf2figma.extract import ExtractInput, ExtractOptions, PdfExtractor
from pdf2figma.ir import ShapeNode
from tests.fixtures import synthetic

pytestmark = pytest.mark.skipif(shutil.which("pdftocairo") is None, reason="poppler not installed")

SVG_NS = "http://www.w3.org/2000/svg"

# Two triangles, far apart, different fills. Triangle A sits at PDF-space
# y 660-700, x 50-90 — a text run at the same PDF-space position overlaps
# it, to prove the donor excludes text even when it's genuinely inside the
# requested region, not just absent by coincidence.
TRIANGLE_A = "0.8 0.1 0.1 rg 50 700 m 90 700 l 70 660 l h f"
TRIANGLE_B = "0.1 0.6 0.1 rg 400 700 m 440 700 l 420 660 l h f"
OVERLAPPING_TEXT = "BT /F1 10 Tf 0 0 0 rg 55 665 Td (Hi) Tj ET"


def _paths(svg: str) -> list[ET.Element]:
    return list(ET.fromstring(svg).iter(f"{{{SVG_NS}}}path"))


_RGB_PERCENT_RE = re.compile(r"rgb\(\s*([\d.]+)%\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*\)")


def _fill_rgbs(svg: str) -> list[tuple[float, float, float]]:
    """Cairo emits `rgb(X%, Y%, Z%)`, not hex — parsed to 0-1 fractions so a
    source hex color can be compared with a rounding tolerance rather than
    an exact string match cairo's own float math won't hit."""
    out = []
    for p in _paths(svg):
        fill = p.get("fill")
        match = _RGB_PERCENT_RE.match(fill) if fill else None
        if match:
            out.append(tuple(float(g) / 100 for g in match.groups()))
    return out


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))


def _contains_color(svg: str, hex_color: str, *, tol: float = 0.01) -> bool:
    target = _hex_to_rgb(hex_color)
    return any(
        all(abs(c - t) < tol for c, t in zip(rgb, target, strict=True)) for rgb in _fill_rgbs(svg)
    )


def _two_triangle_fixture(tmp_path: Path) -> tuple[ShapeNode, ShapeNode, Path, Path]:
    pdf_bytes = synthetic.build_pdf(TRIANGLE_A + " " + TRIANGLE_B + " " + OVERLAPPING_TEXT)

    document = PdfExtractor().extract(ExtractInput(data=pdf_bytes), ExtractOptions())
    paths = sorted(
        (n for n in document.pages[0].nodes if isinstance(n, ShapeNode) and n.shape == "path"),
        key=lambda n: n.bbox.x,
    )
    assert len(paths) == 2, "expected exactly the two triangles, classified as path-kind"
    node_a, node_b = paths

    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(pdf_bytes)
    ir_path = tmp_path / "doc.ir.json"
    ir_path.write_text(json.dumps(document.model_dump(mode="json", exclude_none=True)))
    return node_a, node_b, pdf_path, ir_path


class TestDonorCliEndToEnd:
    def test_two_triangles_produce_isolated_donors_with_no_text(self, tmp_path: Path) -> None:
        node_a, node_b, pdf_path, ir_path = _two_triangle_fixture(tmp_path)
        out_path = tmp_path / "donors.json"

        code = main(
            [
                "convert",
                "donor",
                str(pdf_path),
                str(ir_path),
                "--ids",
                f"{node_a.id},{node_b.id}",
                "-o",
                str(out_path),
            ]
        )
        assert code == 0

        result = json.loads(out_path.read_text())
        donors = {n["id"]: n for n in result["nodes"]}
        assert set(donors) == {node_a.id, node_b.id}

        svg_a, svg_b = donors[node_a.id]["svg"], donors[node_b.id]["svg"]

        fill_a, fill_b = node_a.fill, node_b.fill
        assert fill_a is not None and fill_b is not None
        assert _contains_color(svg_a, fill_a.hex)
        assert not _contains_color(svg_a, fill_b.hex), "triangle B's geometry leaked into A's donor"
        assert _contains_color(svg_b, fill_b.hex)
        assert not _contains_color(svg_b, fill_a.hex), "triangle A's geometry leaked into B's donor"

        # Triangle A's donor overlaps the text run geometrically — it must
        # still carry zero glyph references.
        assert list(ET.fromstring(svg_a).iter(f"{{{SVG_NS}}}use")) == []

        for node, svg in ((node_a, svg_a), (node_b, svg_b)):
            root = ET.fromstring(svg)
            box = node.bbox
            assert root.get("viewBox") == f"{box.x} {box.y} {box.w} {box.h}"

    def test_omitting_ids_selects_every_path_kind_node_on_the_page(self, tmp_path: Path) -> None:
        """Curating `--ids` by hand doesn't scale once a real report turns
        out to have well over a hundred `path` nodes on one page (measured
        against a real document) — the default
        with no `--ids` is every `path`-kind node, not a filtered subset."""
        node_a, node_b, pdf_path, ir_path = _two_triangle_fixture(tmp_path)
        out_path = tmp_path / "donors.json"

        code = main(["convert", "donor", str(pdf_path), str(ir_path), "-o", str(out_path)])
        assert code == 0

        result = json.loads(out_path.read_text())
        assert {n["id"] for n in result["nodes"]} == {node_a.id, node_b.id}

    def test_no_ids_and_no_path_nodes_is_a_clear_error(self, tmp_path: Path) -> None:
        pdf_bytes = synthetic.build_pdf(synthetic.RECT)
        document = PdfExtractor().extract(ExtractInput(data=pdf_bytes), ExtractOptions())

        pdf_path = tmp_path / "doc.pdf"
        pdf_path.write_bytes(pdf_bytes)
        ir_path = tmp_path / "doc.ir.json"
        ir_path.write_text(json.dumps(document.model_dump(mode="json", exclude_none=True)))

        code = main(
            ["convert", "donor", str(pdf_path), str(ir_path), "-o", str(tmp_path / "out.json")]
        )
        assert code == 1
