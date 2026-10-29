"""Structural diff: exact, per-node comparison against synthetic fixtures."""

from __future__ import annotations

import pytest

from pdf2figma.ir import Color, Stroke
from pdf2figma.verify import (
    BUILT_VERSION,
    BuiltDocument,
    BuiltFont,
    BuiltNode,
    BuiltPage,
    BuiltVersionError,
    StructuralTolerances,
    diff_structural,
    load_built,
    payload_notes_for,
)
from tests.fixtures import synthetic_ir as fx

TOL = StructuralTolerances(bbox=0.5)


def _built(*nodes: BuiltNode) -> BuiltDocument:
    page = BuiltPage(width=200, height=200)
    return BuiltDocument(built_version=BUILT_VERSION, page=page, nodes=list(nodes))


class TestDiffStructural:
    def test_exact_match_is_matched(self) -> None:
        source = [fx.rect_node("r1", 0, 0, 100, 50, fill=fx.CARD_FILL)]
        built = _built(BuiltNode(id="r1", bbox=source[0].bbox, fill=fx.CARD_FILL))
        report = diff_structural(source, built, TOL)
        assert [r.status for r in report.regions] == ["matched"]
        assert report.counts.matched == 1

    def test_bbox_within_tolerance_is_matched(self) -> None:
        source = [fx.rect_node("r1", 0, 0, 100, 50, fill=fx.CARD_FILL)]
        shifted = fx.BBox(x=0.3, y=0, w=100, h=50)
        built = _built(BuiltNode(id="r1", bbox=shifted, fill=fx.CARD_FILL))
        report = diff_structural(source, built, TOL)
        assert report.regions[0].status == "matched"
        assert report.regions[0].bbox_delta == pytest.approx(0.3)

    def test_bbox_beyond_tolerance_is_mismatched(self) -> None:
        source = [fx.rect_node("r1", 0, 0, 100, 50, fill=fx.CARD_FILL)]
        shifted = fx.BBox(x=5, y=0, w=100, h=50)
        built = _built(BuiltNode(id="r1", bbox=shifted, fill=fx.CARD_FILL))
        report = diff_structural(source, built, TOL)
        assert report.regions[0].status == "mismatched"
        assert "bbox delta" in report.regions[0].notes[0]

    def test_shape_fill_mismatch_is_reported(self) -> None:
        source = [fx.rect_node("r1", 0, 0, 100, 50, fill=fx.CARD_FILL)]
        built = _built(BuiltNode(id="r1", bbox=source[0].bbox, fill="#990000"))
        report = diff_structural(source, built, TOL)
        assert report.regions[0].status == "mismatched"
        assert report.regions[0].notes == [f"fill '#990000', expected '{fx.CARD_FILL}'"]

    def test_stroke_mismatch_is_reported(self) -> None:
        source = [fx.shape_node("l1", "line", 0, 0, 100, 0, fill=None)]
        built = _built(BuiltNode(id="l1", bbox=source[0].bbox, stroke_color="#ff0000"))
        report = diff_structural(source, built, TOL)
        assert report.regions[0].status == "mismatched"
        assert "stroke" in report.regions[0].notes[0]

    def test_text_content_mismatch_is_reported(self) -> None:
        source = [fx.text_node("t1", 0, 0, 100, 20, "expected")]
        built = _built(BuiltNode(id="t1", bbox=source[0].bbox, fill=fx.HEADER_COLOR, text="actual"))
        report = diff_structural(source, built, TOL)
        assert report.regions[0].status == "mismatched"
        assert "text 'actual', expected 'expected'" in report.regions[0].notes

    def test_font_size_mismatch_is_reported(self) -> None:
        # A unit slip (points painted as pixels) shrinks every text to 75%.
        source = [fx.text_node("t1", 0, 0, 100, 20, "Hi", size=12.0)]
        built = _built(
            BuiltNode(
                id="t1",
                bbox=source[0].bbox,
                fill=fx.HEADER_COLOR,
                text="Hi",
                font=BuiltFont(family="Helvetica", size=9.0),
            )
        )
        report = diff_structural(source, built, TOL)
        assert report.regions[0].status == "mismatched"
        assert "font size 9pt, expected 12pt" in report.regions[0].notes

    def test_stroke_width_mismatch_is_reported(self) -> None:
        line = fx.shape_node("l1", "line", 0, 0, 100, 0, fill=None)
        stroke = Stroke(color=Color(hex="#000000"), width=0.75)
        source = [line.model_copy(update={"stroke": stroke})]
        built = _built(
            BuiltNode(id="l1", bbox=line.bbox, stroke_color="#000000", stroke_width=1.0)
        )
        report = diff_structural(source, built, TOL)
        assert report.regions[0].status == "mismatched"
        assert "stroke width 1pt, expected 0.75pt" in report.regions[0].notes

    def test_source_node_absent_from_built_is_missing(self) -> None:
        source = [fx.rect_node("gone", 0, 0, 10, 10, fill="#000000")]
        report = diff_structural(source, _built(), TOL)
        assert report.regions[0].status == "missing"
        assert report.counts.missing == 1

    def test_built_id_absent_from_source_is_extra(self) -> None:
        built = _built(BuiltNode(id="surprise", bbox=fx.BBox(x=0, y=0, w=1, h=1)))
        report = diff_structural([], built, TOL)
        assert report.regions[0].status == "extra"
        assert report.counts.extra == 1

    def test_counts_match_the_region_list(self) -> None:
        source = [
            fx.rect_node("matched1", 0, 0, 10, 10, fill="#000000"),
            fx.rect_node("gone", 0, 0, 10, 10, fill="#000000"),
        ]
        built = _built(
            BuiltNode(id="matched1", bbox=source[0].bbox, fill="#000000"),
            BuiltNode(id="surprise", bbox=fx.BBox(x=0, y=0, w=1, h=1)),
        )
        report = diff_structural(source, built, TOL)
        statuses = [r.status for r in report.regions]
        assert report.counts.matched == statuses.count("matched")
        assert report.counts.missing == statuses.count("missing")
        assert report.counts.extra == statuses.count("extra")


class TestPayloadEnrichment:
    def test_unsupported_reason_is_attached(self) -> None:
        node = {"id": "p1", "kind": "unsupported", "unsupportedReason": "path-geometry-unavailable"}
        payload_data = {"nodes": [node]}
        source = [fx.shape_node("p1", "path", 0, 0, 10, 10, fill=None)]
        report = diff_structural(source, _built(), TOL, payload_data)
        assert report.regions[0].notes == ["payload: path-geometry-unavailable"]

    def test_missing_reason_falls_back_to_context(self) -> None:
        payload_data = {
            "nodes": [
                {
                    "id": "t1",
                    "kind": "text",
                    "candidateId": None,
                    "font": {"family": "MadeUpFont", "size": 12, "italic": False},
                }
            ]
        }
        source = [fx.text_node("t1", 0, 0, 100, 20, "hello")]
        report = diff_structural(source, _built(), TOL, payload_data)
        note = report.regions[0].notes[0]
        assert "kind=text" in note
        assert "font=MadeUpFont" in note
        assert "no unsupportedReason recorded" in note

    def test_no_payload_means_no_enrichment(self) -> None:
        source = [fx.rect_node("gone", 0, 0, 10, 10, fill="#000000")]
        report = diff_structural(source, _built(), TOL)
        assert report.regions[0].notes == []

    def test_payload_notes_for_unknown_id_is_empty(self) -> None:
        assert payload_notes_for({"nodes": []}, "nope") == []


class TestBuiltVersioning:
    def test_round_trip(self) -> None:
        doc = _built(BuiltNode(id="a", bbox=fx.BBox(x=0, y=0, w=1, h=1)))
        assert load_built(doc.model_dump(mode="json")).built_version == BUILT_VERSION

    def test_foreign_version_is_refused(self) -> None:
        payload = _built().model_dump(mode="json")
        payload["built_version"] = "99.0"
        with pytest.raises(BuiltVersionError, match=r"99\.0"):
            load_built(payload)
