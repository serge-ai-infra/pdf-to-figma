"""Extraction tests against PDFs whose contents we chose.

The assertions that matter here are the ones nobody notices when they break:
coordinate conversion, color normalization and run grouping. A wrong bbox still
produces a plausible-looking IR.
"""

from __future__ import annotations

import pytest

from pdf2figma.extract import ExtractError, ExtractInput, ExtractOptions, PdfExtractor
from pdf2figma.extract.pdf import _font_of
from pdf2figma.ir import ShapeNode, TextNode
from tests.fixtures import synthetic

EPSILON = 0.01


def extract(content: str, **kwargs: object) -> tuple[list[object], ExtractOptions]:
    options = ExtractOptions(**kwargs)  # type: ignore[arg-type]
    document = PdfExtractor().extract(ExtractInput(data=synthetic.build_pdf(content)), options)
    return list(document.pages[0].nodes), options


def shapes(nodes: list[object]) -> list[ShapeNode]:
    return [n for n in nodes if isinstance(n, ShapeNode)]


def texts(nodes: list[object]) -> list[TextNode]:
    return [n for n in nodes if isinstance(n, TextNode)]


class TestGeometry:
    def test_rect_converts_to_top_left_origin(self) -> None:
        nodes, _ = extract(synthetic.RECT)
        rects = [s for s in shapes(nodes) if s.shape == "rect"]
        assert len(rects) == 1

        box = rects[0].bbox
        want = synthetic.RECT_EXPECTED
        assert box.x == pytest.approx(want["x"], abs=EPSILON)
        assert box.y == pytest.approx(want["y"], abs=EPSILON), (
            "y must be measured from the top of the page, not the PDF's bottom-up origin"
        )
        assert box.w == pytest.approx(want["w"], abs=EPSILON)
        assert box.h == pytest.approx(want["h"], abs=EPSILON)

    def test_every_node_sits_inside_its_page(self) -> None:
        nodes, _ = extract(synthetic.RECT + " " + synthetic.LINE + " " + synthetic.TEXT)
        for node in nodes:
            box = node.bbox  # type: ignore[attr-defined]
            assert box.x >= -EPSILON
            assert box.y >= -EPSILON
            assert box.right <= synthetic.PAGE_WIDTH + EPSILON
            assert box.bottom <= synthetic.PAGE_HEIGHT + EPSILON

    def test_page_dimensions_are_reported(self) -> None:
        document = PdfExtractor().extract(
            ExtractInput(data=synthetic.build_pdf(synthetic.RECT)), ExtractOptions()
        )
        page = document.pages[0]
        assert page.width == pytest.approx(synthetic.PAGE_WIDTH)
        assert page.height == pytest.approx(synthetic.PAGE_HEIGHT)


class TestColor:
    def test_fill_normalizes_to_srgb_hex(self) -> None:
        nodes, _ = extract(synthetic.RECT)
        rect = next(s for s in shapes(nodes) if s.shape == "rect")
        assert rect.fill is not None
        assert rect.fill.hex == synthetic.RECT_EXPECTED["hex"]

    def test_text_color_is_exact_not_inferred(self) -> None:
        nodes, _ = extract(synthetic.TEXT)
        run = texts(nodes)[0]
        assert run.color is not None
        assert run.color.hex == synthetic.TEXT_EXPECTED["hex"]
        assert run.color_confidence == "exact"

    def test_disabling_color_marks_it_unknown_rather_than_guessing(self) -> None:
        nodes, _ = extract(synthetic.TEXT, text_color=False)
        run = texts(nodes)[0]
        assert run.color is None
        assert run.color_confidence == "unknown"


class TestClassification:
    def test_stroked_line_is_a_line(self) -> None:
        nodes, _ = extract(synthetic.LINE)
        assert [s.shape for s in shapes(nodes)] == ["line"]

    def test_line_keeps_its_stroke(self) -> None:
        nodes, _ = extract(synthetic.LINE)
        stroke = shapes(nodes)[0].stroke
        assert stroke is not None
        assert stroke.color.hex == "#0000ff"
        assert stroke.width == pytest.approx(2.0, abs=EPSILON)


class TestText:
    def test_run_carries_text_font_and_size(self) -> None:
        nodes, _ = extract(synthetic.TEXT)
        run = texts(nodes)[0]
        want = synthetic.TEXT_EXPECTED
        assert run.text == want["text"]
        assert run.font.size == pytest.approx(want["size"], abs=EPSILON)
        assert want["family"] in run.font.family

    def test_distant_words_do_not_merge(self) -> None:
        nodes, _ = extract(synthetic.TWO_RUNS)
        collected = sorted(run.text for run in texts(nodes))
        assert collected == ["Left", "Right"]

    def test_run_gap_ratio_is_a_parameter(self) -> None:
        """Grouping is our inference, so its threshold must be tunable, not baked in."""
        merged, _ = extract(synthetic.TWO_RUNS, run_gap_ratio=100.0)
        assert [run.text for run in texts(merged)] == ["LeftRight"]


class TestFontName:
    """Standard-14 PostScript names bolt style onto family with a hyphen —
    Figma's loadFontAsync wants family/style split, not "Helvetica-Bold" as
    one literal family it has never heard of."""

    @pytest.mark.parametrize(
        ("fontname", "family", "weight", "italic"),
        [
            ("Helvetica-Bold", "Helvetica", 700, False),
            ("Helvetica", "Helvetica", None, False),
            ("Times-BoldItalic", "Times", 700, True),
            ("Times-Italic", "Times", None, True),
            ("Courier-Oblique", "Courier", None, True),
            ("ZapfDingbats", "ZapfDingbats", None, False),
            ("ABCDEF+Helvetica-Bold", "Helvetica", 700, False),
        ],
    )
    def test_strips_style_suffix_from_family(
        self, fontname: str, family: str, weight: int | None, italic: bool
    ) -> None:
        font = _font_of({"fontname": fontname, "size": 12.0})
        assert font.family == family
        assert font.weight == weight
        assert font.italic == italic

    def test_does_not_truncate_a_genuinely_hyphenated_family(self) -> None:
        font = _font_of({"fontname": "Franklin-Gothic", "size": 12.0})
        assert font.family == "Franklin-Gothic"


class TestFontNameEndToEnd:
    """`TestFontName` above pins `_font_of` in isolation. This pins the same
    behavior through the real entry point — a PDF whose embedded font is
    genuinely named "Helvetica-Bold" (not a hand-built dict), run through
    `PdfExtractor().extract()` — so a regression in *how* `_font_of` gets
    called (wrong field read, grouping bypassing it, whatever) fails here
    even if `_font_of` itself is still correct in isolation."""

    def test_extract_strips_the_style_suffix_from_a_real_pdf(self) -> None:
        document = PdfExtractor().extract(
            ExtractInput(data=synthetic.build_pdf(synthetic.TEXT, font_name="Helvetica-Bold")),
            ExtractOptions(),
        )
        found = texts(list(document.pages[0].nodes))
        assert len(found) == 1
        assert found[0].font.family == "Helvetica"
        assert found[0].font.weight == 700


class TestSelection:
    def test_pages_option_selects_a_subset(self) -> None:
        document = PdfExtractor().extract(
            ExtractInput(data=synthetic.build_pdf(synthetic.RECT, pages=3)),
            ExtractOptions(pages=(1,)),
        )
        assert [page.index for page in document.pages] == [1]
        assert document.source.page_count == 3, "the source count reports the whole document"


class TestFailures:
    def test_non_pdf_is_rejected_clearly(self) -> None:
        with pytest.raises(ExtractError, match="Not a PDF"):
            PdfExtractor().extract(ExtractInput(data=b"just some bytes"), ExtractOptions())

    def test_truncated_pdf_raises_extract_error(self) -> None:
        broken = synthetic.build_pdf(synthetic.RECT)[:120]
        with pytest.raises(ExtractError):
            PdfExtractor().extract(ExtractInput(data=broken), ExtractOptions())
