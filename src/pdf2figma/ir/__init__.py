"""Intermediate representation — the contract every stage reads and writes."""

from pdf2figma.ir.model import (
    IR_VERSION,
    BBox,
    Color,
    Confidence,
    Document,
    Font,
    ImageNode,
    IRVersionError,
    Node,
    Page,
    ShapeKind,
    ShapeNode,
    SourceInfo,
    Stroke,
    TextNode,
    load,
)

__all__ = [
    "IR_VERSION",
    "BBox",
    "Color",
    "Confidence",
    "Document",
    "Font",
    "IRVersionError",
    "ImageNode",
    "Node",
    "Page",
    "ShapeKind",
    "ShapeNode",
    "SourceInfo",
    "Stroke",
    "TextNode",
    "load",
]
