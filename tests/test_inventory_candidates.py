"""Shape and text atom candidates against synthetic corpora."""

from __future__ import annotations

import pytest

from pdf2figma.inventory.candidates import build_shape_candidates, build_text_candidates
from pdf2figma.inventory.model import ShapeCandidate, TextCandidate
from pdf2figma.inventory.tokens import build_palette, build_type_scale
from tests.fixtures import synthetic_ir as fx


def _build(
    documents: list[fx.Document],
    *,
    color_tol: float = 6.0,
    size_tol: float = 0.5,
    min_occurrences: int = 2,
) -> tuple[list[ShapeCandidate], int, list[TextCandidate], int]:
    palette = build_palette(documents, color_tol)
    type_scale = build_type_scale(documents, size_tol)
    shapes, unclustered_shapes = build_shape_candidates(
        documents, palette, size_tol, min_occurrences
    )
    texts, unclustered_text = build_text_candidates(documents, palette, type_scale, min_occurrences)
    return shapes, unclustered_shapes, texts, unclustered_text


class TestShapeCandidates:
    def test_recurring_card_becomes_a_candidate(self) -> None:
        shapes, _, _, _ = _build(fx.card_corpus())
        standard = next(c for c in shapes if c.fill == fx.CARD_FILL)
        assert standard.shape == "rect"
        assert standard.count == 9  # 3 standard cards x 3 documents
        assert standard.documents == 3
        assert standard.presence_ratio == pytest.approx(1.0)
        assert standard.variant is False
        assert standard.width == pytest.approx(fx.CARD_WIDTH)
        assert standard.height == pytest.approx(fx.CARD_HEIGHT)

    def test_card_present_in_a_subset_of_documents_is_a_variant(self) -> None:
        shapes, _, _, _ = _build(fx.card_corpus())
        extra = next(c for c in shapes if c.fill == fx.EXTRA_CARD_FILL)
        assert extra.count == 2
        assert extra.documents == 2
        assert extra.presence_ratio == pytest.approx(2 / 3)
        assert extra.variant is True

    def test_one_off_shape_is_not_reported_as_a_candidate(self) -> None:
        shapes, unclustered, _, _ = _build(fx.card_corpus())
        assert all(c.fill != fx.ONE_OFF_FILL for c in shapes)
        assert unclustered >= 1

    def test_sizes_further_apart_than_tolerance_stay_separate(self) -> None:
        small = [
            fx.document_of(fx.page_of([fx.rect_node(f"s{i}", 0, 0, 100, 50, fill="#123456")]))
            for i in range(2)
        ]
        large = [
            fx.document_of(fx.page_of([fx.rect_node(f"l{i}", 0, 0, 100, 90, fill="#123456")]))
            for i in range(2)
        ]
        shapes, unclustered, _, _ = _build(small + large, size_tol=1.0)
        assert len(shapes) == 2
        assert unclustered == 0

    def test_below_min_occurrences_is_not_a_candidate(self) -> None:
        docs = [fx.document_of(fx.page_of([fx.rect_node("only", 0, 0, 10, 10, fill="#abcdef")]))]
        shapes, unclustered, _, _ = _build(docs, min_occurrences=2)
        assert shapes == []
        assert unclustered == 1

    def test_occurrences_are_capped_while_count_stays_exact(self) -> None:
        docs = [
            fx.document_of(fx.page_of([fx.rect_node(f"r{i}", 0, 0, 10, 10, fill="#123456")]))
            for i in range(25)
        ]
        shapes, _, _, _ = _build(docs)
        assert len(shapes) == 1
        assert shapes[0].count == 25
        assert len(shapes[0].occurrences) == 20


class TestTextCandidates:
    def test_recurring_style_reports_distinct_content_as_a_sample(self) -> None:
        _, _, texts, _ = _build(fx.card_corpus())
        assert len(texts) == 1
        header = texts[0]
        assert header.count == 3
        assert header.documents == 3
        assert header.variant is False
        assert set(header.sample_texts) == {"Report — Q1", "Report — Q2", "Report — Q3"}

    def test_sample_texts_are_capped_while_count_stays_exact(self) -> None:
        docs = [
            fx.document_of(fx.page_of([fx.text_node(f"t{i}", 0, 0, 50, 10, f"Row {i}")]))
            for i in range(15)
        ]
        _, _, texts, _ = _build(docs)
        assert len(texts) == 1
        assert texts[0].count == 15
        assert len(texts[0].sample_texts) == 10
