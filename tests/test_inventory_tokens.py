"""Palette, type scale and spacing against synthetic corpora."""

from __future__ import annotations

import pytest

from pdf2figma.inventory.tokens import build_palette, build_spacing, build_type_scale
from tests.fixtures import synthetic_ir as fx


class TestPalette:
    def test_counts_every_role_for_a_shared_color(self) -> None:
        result = build_palette(fx.card_corpus(), tolerance=6.0)
        card_token = next(t for t in result.tokens if t.hex == fx.CARD_FILL)
        assert card_token.count == 9  # 3 standard cards x 3 documents
        assert card_token.roles == {"fill": 9}

    def test_colors_within_tolerance_merge(self) -> None:
        docs = [_single_fill_doc("#000000"), _single_fill_doc("#000005")]
        result = build_palette(docs, tolerance=6.0)
        assert len(result.tokens) == 1
        assert result.tokens[0].count == 2

    def test_colors_beyond_tolerance_stay_separate(self) -> None:
        docs = [_single_fill_doc("#000000"), _single_fill_doc("#0000ff")]
        result = build_palette(docs, tolerance=6.0)
        assert len(result.tokens) == 2

    def test_cluster_of_maps_every_seen_hex_to_its_own_token(self) -> None:
        result = build_palette(fx.card_corpus(), tolerance=6.0)
        for hex_value in (fx.CARD_FILL, fx.EXTRA_CARD_FILL, fx.HEADER_COLOR, fx.ONE_OFF_FILL):
            index = result.cluster_of[hex_value]
            assert result.tokens[index].hex == hex_value


class TestTypeScale:
    def test_groups_by_exact_family_weight_italic(self) -> None:
        result = build_type_scale(fx.card_corpus(), tolerance=0.5)
        assert len(result.tokens) == 1
        token = result.tokens[0]
        assert token.family == "Helvetica"
        assert token.size == pytest.approx(12.0)
        assert token.count == 3  # one header per document

    def test_different_families_never_merge(self) -> None:
        helvetica = fx.text_node("t1", 0, 0, 10, 10, "A", family="Helvetica", size=12)
        times = fx.text_node("t2", 0, 0, 10, 10, "B", family="Times", size=12)
        docs = [fx.document_of(fx.page_of([helvetica])), fx.document_of(fx.page_of([times]))]
        result = build_type_scale(docs, tolerance=0.5)
        assert len(result.tokens) == 2

    def test_sizes_within_tolerance_merge(self) -> None:
        docs = [
            fx.document_of(fx.page_of([fx.text_node("t1", 0, 0, 10, 10, "A", size=12.0)])),
            fx.document_of(fx.page_of([fx.text_node("t2", 0, 0, 10, 10, "B", size=12.3)])),
        ]
        result = build_type_scale(docs, tolerance=0.5)
        assert len(result.tokens) == 1
        assert result.tokens[0].count == 2


class TestSpacing:
    def test_finds_the_repeated_card_gap(self) -> None:
        tokens = build_spacing(fx.card_corpus(), tolerance=1.0)
        x_tokens = [t for t in tokens if t.axis == "x"]
        dominant = max(x_tokens, key=lambda t: t.count)
        assert dominant.gap == pytest.approx(fx.CARD_GAP, abs=1.0)
        # 2 gaps among the 3 standard cards per doc x 3 docs, plus 1 extra gap
        # (card2 -> the variant card) in the 2 documents that have it: 6 + 2 = 8
        assert dominant.count == 8


def _single_fill_doc(hex_value: str) -> fx.Document:
    return fx.document_of(fx.page_of([fx.rect_node("r", 0, 0, 10, 10, fill=hex_value)]))
