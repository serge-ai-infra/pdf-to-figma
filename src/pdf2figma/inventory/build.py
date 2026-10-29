"""Orchestrates one inventory pass: a corpus of IR documents in, a report out.

Tokens are built first because candidates reuse their color and size clusters
— see `tokens.py` for why that ordering is load-bearing, not incidental.
"""

from __future__ import annotations

from collections.abc import Sequence

from pdf2figma.inventory.candidates import build_shape_candidates, build_text_candidates
from pdf2figma.inventory.model import CorpusStats, Inventory, Tolerances
from pdf2figma.inventory.tokens import build_palette, build_spacing, build_type_scale
from pdf2figma.ir import Document


def build_inventory(documents: Sequence[Document], tolerances: Tolerances) -> Inventory:
    palette = build_palette(documents, tolerances.color)
    type_scale = build_type_scale(documents, tolerances.size)
    spacing = build_spacing(documents, tolerances.spacing)

    shape_candidates, unclustered_shapes = build_shape_candidates(
        documents, palette, tolerances.size, tolerances.min_occurrences
    )
    text_candidates, unclustered_text = build_text_candidates(
        documents, palette, type_scale, tolerances.min_occurrences
    )

    corpus = CorpusStats(
        documents=len(documents),
        pages=sum(len(document.pages) for document in documents),
        nodes=sum(document.node_count() for document in documents),
    )

    return Inventory(
        corpus=corpus,
        tolerances=tolerances,
        palette=palette.tokens,
        type_scale=type_scale.tokens,
        spacing=spacing,
        shape_candidates=shape_candidates,
        text_candidates=text_candidates,
        unclustered_shapes=unclustered_shapes,
        unclustered_text=unclustered_text,
    )
