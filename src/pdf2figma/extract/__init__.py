"""Extraction — document bytes in, IR out."""

from pdf2figma.extract.base import (
    ExtractError,
    ExtractInput,
    ExtractOptions,
    Extractor,
)
from pdf2figma.extract.pdf import PdfExtractor

__all__ = [
    "ExtractError",
    "ExtractInput",
    "ExtractOptions",
    "Extractor",
    "PdfExtractor",
]
