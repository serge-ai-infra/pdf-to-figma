"""`page_to_svg` against a real `pdftocairo` process — the one integration
test in this package. Skips cleanly where poppler isn't installed, same
posture S1's own cross-check against `pdftocairo -svg` already takes.
"""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET

import pytest

from pdf2figma.convert.poppler import ConvertError, page_to_svg
from tests.fixtures import synthetic

pytestmark = pytest.mark.skipif(shutil.which("pdftocairo") is None, reason="poppler not installed")


def _page_size(svg: str) -> tuple[str, str, str]:
    """Root viewBox plus width/height with any `pt` unit stripped.

    Cairo's root units vary by version: macOS Homebrew's writes `width="400pt"`,
    Ubuntu's writes a unitless `width="400"`. Nothing downstream reads them
    (`crop_to_donor` rewrites the root), so the test pins the viewBox, which is
    what the donor crop actually relies on, and accepts either unit form.
    """
    root = ET.fromstring(svg.encode())
    return (
        root.get("viewBox", ""),
        root.get("width", "").removesuffix("pt"),
        root.get("height", "").removesuffix("pt"),
    )


class TestPageToSvg:
    def test_converts_a_real_pdf_page_to_svg_at_its_own_page_size(self) -> None:
        pdf_bytes = synthetic.build_pdf(synthetic.RECT, width=400.0, height=300.0)
        svg = page_to_svg(pdf_bytes, page=1)
        assert svg.startswith("<?xml")
        assert _page_size(svg) == ("0 0 400 300", "400", "300")

    def test_selects_the_requested_page_of_a_multi_page_pdf(self) -> None:
        pdf_bytes = synthetic.build_pdf(synthetic.RECT, pages=3)
        svg = page_to_svg(pdf_bytes, page=2)
        assert _page_size(svg) == ("0 0 612 792", "612", "792")

    def test_out_of_range_page_raises_convert_error(self) -> None:
        pdf_bytes = synthetic.build_pdf(synthetic.RECT, pages=1)
        with pytest.raises(ConvertError):
            page_to_svg(pdf_bytes, page=5)
