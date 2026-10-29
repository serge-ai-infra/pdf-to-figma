"""Geometry donor — crop a PDF page's SVG conversion down to one region.

`path`-kind IR shapes carry no contour (S1's classifier: bbox only), so
nothing downstream can rebuild them. This is the tool that inherits their
geometry from the PDF's own SVG conversion instead — see
`docs/specs/s3.5-geometry-donor/spec.md`.
"""

from pdf2figma.convert.donor import crop_to_donor
from pdf2figma.convert.model import CONVERT_VERSION, DonorNode, DonorSet
from pdf2figma.convert.poppler import ConvertError, page_to_svg

__all__ = [
    "CONVERT_VERSION",
    "ConvertError",
    "DonorNode",
    "DonorSet",
    "crop_to_donor",
    "page_to_svg",
]
