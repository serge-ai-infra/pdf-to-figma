"""Synthetic IR documents, built directly as pydantic objects.

No PDF bytes needed here — this stage consumes IR, not PDF. `card_corpus()`
models "the same template, several documents": a header whose style is fixed
and content varies, a row of repeated card rects with a fixed gap between
them, one card present in only a subset of the corpus, and one genuinely
one-off shape — exactly the distinctions S2 exists to make.
"""

from __future__ import annotations

from pdf2figma.ir import (
    BBox,
    Color,
    Document,
    Font,
    Node,
    Page,
    ShapeKind,
    ShapeNode,
    SourceInfo,
    TextNode,
)

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0

CARD_FILL = "#3355ff"
EXTRA_CARD_FILL = "#ff9900"
HEADER_COLOR = "#111111"
ONE_OFF_FILL = "#00cc44"

CARD_GAP = 20.0
CARD_WIDTH = 100.0
CARD_HEIGHT = 50.0
CARD_Y = 150.0


def shape_node(
    node_id: str,
    shape: ShapeKind,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fill: str | None,
    z: int = 0,
) -> ShapeNode:
    return ShapeNode(
        id=node_id,
        bbox=BBox(x=x, y=y, w=w, h=h),
        z=z,
        shape=shape,
        fill=Color(hex=fill) if fill else None,
    )


def rect_node(
    node_id: str, x: float, y: float, w: float, h: float, *, fill: str | None, z: int = 0
) -> ShapeNode:
    return shape_node(node_id, "rect", x, y, w, h, fill=fill, z=z)


def text_node(
    node_id: str,
    x: float,
    y: float,
    w: float,
    h: float,
    content: str,
    *,
    family: str = "Helvetica",
    size: float = 12.0,
    color: str | None = HEADER_COLOR,
    z: int = 0,
) -> TextNode:
    return TextNode(
        id=node_id,
        bbox=BBox(x=x, y=y, w=w, h=h),
        z=z,
        text=content,
        font=Font(family=family, size=size),
        color=Color(hex=color) if color else None,
        color_confidence="exact" if color else "unknown",
    )


def page_of(nodes: list[Node], *, index: int = 0) -> Page:
    return Page(index=index, width=PAGE_WIDTH, height=PAGE_HEIGHT, nodes=nodes)


def document_of(*pages: Page, page_count: int | None = None) -> Document:
    return Document(source=SourceInfo(page_count=page_count or len(pages)), pages=list(pages))


def card_corpus() -> list[Document]:
    """3 documents sharing a template: a varying header, 3 standard cards, a
    distinctly-styled card present in only 2 of the 3 documents (a variant),
    and (document 0 only) one shape that never recurs at all.
    """
    documents: list[Document] = []
    headers = ["Report — Q1", "Report — Q2", "Report — Q3"]

    for doc_index, header_text in enumerate(headers):
        nodes: list[Node] = [
            text_node(f"d{doc_index}.header", 50, 50, 200, 20, header_text),
        ]

        for card_index in range(3):
            x = 50 + card_index * (CARD_WIDTH + CARD_GAP)
            card_id = f"d{doc_index}.card{card_index}"
            nodes.append(rect_node(card_id, x, CARD_Y, CARD_WIDTH, CARD_HEIGHT, fill=CARD_FILL))

        if doc_index in (0, 1):
            extra_x = 50 + 3 * (CARD_WIDTH + CARD_GAP)
            extra_id = f"d{doc_index}.card3"
            extra = rect_node(
                extra_id, extra_x, CARD_Y, CARD_WIDTH, CARD_HEIGHT, fill=EXTRA_CARD_FILL
            )
            nodes.append(extra)

        if doc_index == 0:
            nodes.append(
                shape_node(f"d{doc_index}.oneoff", "ellipse", 500, 700, 30, 30, fill=ONE_OFF_FILL)
            )

        documents.append(document_of(page_of(nodes, index=0)))

    return documents
