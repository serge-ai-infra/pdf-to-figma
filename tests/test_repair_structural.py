"""Deterministic pattern-grouping against hand-built structural reports."""

from __future__ import annotations

from pdf2figma.repair import triage_structural
from pdf2figma.verify import (
    RegionStatus,
    StructuralCounts,
    StructuralRegion,
    StructuralReport,
    StructuralTolerances,
)

TOL = StructuralTolerances(bbox=0.5)


def _region(id: str, status: RegionStatus, notes: list[str] | None = None) -> StructuralRegion:
    return StructuralRegion(id=id, status=status, notes=notes or [])


def _report(*regions: StructuralRegion) -> StructuralReport:
    counts = StructuralCounts(
        matched=sum(1 for r in regions if r.status == "matched"),
        mismatched=sum(1 for r in regions if r.status == "mismatched"),
        missing=sum(1 for r in regions if r.status == "missing"),
        extra=sum(1 for r in regions if r.status == "extra"),
    )
    return StructuralReport(tolerances=TOL, counts=counts, regions=list(regions))


class TestClassification:
    def test_pattern_recurring_at_the_threshold_is_systemic(self) -> None:
        report = _report(
            _region("a", "mismatched", ["fill '#000', expected '#fff'"]),
            _region("b", "mismatched", ["fill '#111', expected '#eee'"]),
        )
        result = triage_structural([report], systemic_threshold=2)
        assert len(result.patterns) == 1
        assert result.patterns[0].classification == "systemic"
        assert result.patterns[0].count == 2

    def test_isolated_pattern_stays_one_off(self) -> None:
        report = _report(_region("a", "mismatched", ["fill '#000', expected '#fff'"]))
        result = triage_structural([report], systemic_threshold=2)
        assert result.patterns[0].classification == "one-off"

    def test_matched_regions_are_never_triaged(self) -> None:
        report = _report(_region("a", "matched"))
        result = triage_structural([report])
        assert result.patterns == []


class TestPatternKeys:
    def test_missing_with_payload_reason_keys_on_it(self) -> None:
        report = _report(_region("a", "missing", ["payload: path-geometry-unavailable"]))
        result = triage_structural([report], systemic_threshold=1)
        assert result.patterns[0].pattern_key == "missing:path-geometry-unavailable"

    def test_missing_without_context_keys_on_no_context(self) -> None:
        report = _report(_region("a", "missing", []))
        result = triage_structural([report], systemic_threshold=1)
        assert result.patterns[0].pattern_key == "missing:no-context"

    def test_missing_reason_mentioning_a_field_name_gets_the_missing_hint(self) -> None:
        """Regression: a build-time skip's context note can contain "kind=text" —
        the hint must not be picked up as a "text content mismatch" hint just
        because the substring "text" appears in the pattern key."""
        note = "payload: kind=text, font=Foo — no unsupportedReason recorded, a build-time skip"
        report = _report(_region("a", "missing", [note]))
        result = triage_structural([report], systemic_threshold=1)
        assert result.patterns[0].pattern_key == "missing:kind=text"
        assert "S4 skip" in (result.patterns[0].hint or "")
        assert "text content mismatch" not in (result.patterns[0].hint or "")

    def test_region_wrong_two_ways_contributes_to_the_combined_pattern(self) -> None:
        notes = ["bbox delta 5.00pt, expected within 0.5pt", "fill '#000', expected '#fff'"]
        report = _report(_region("a", "mismatched", notes))
        result = triage_structural([report], systemic_threshold=1)
        assert [p.pattern_key for p in result.patterns] == ["mismatched:bbox+fill"]

    def test_extra_gets_its_own_pattern(self) -> None:
        report = _report(_region("surprise", "extra"))
        result = triage_structural([report], systemic_threshold=1)
        assert result.patterns[0].pattern_key == "extra"
        assert result.patterns[0].hint is not None


class TestCrossReportTriage:
    def test_pattern_spanning_multiple_reports_is_triaged_together(self) -> None:
        report_a = _report(_region("a", "mismatched", ["fill '#000', expected '#fff'"]))
        report_b = _report(_region("a", "mismatched", ["fill '#111', expected '#eee'"]))

        result = triage_structural([report_a, report_b], systemic_threshold=2)
        assert len(result.patterns) == 1
        assert result.patterns[0].classification == "systemic"

    def test_occurrence_document_indexing_matches_input_order(self) -> None:
        report_a = _report(_region("a", "missing"))
        report_b = _report(_region("a", "missing"))  # same id, different document

        result = triage_structural([report_a, report_b], systemic_threshold=1)
        occurrences = result.patterns[0].occurrences
        assert {(o.document, o.id) for o in occurrences} == {(0, "a"), (1, "a")}


class TestHints:
    def test_known_pattern_kinds_carry_a_hint(self) -> None:
        for notes, expected_substring in [
            (["bbox delta 5.00pt, expected within 0.5pt"], "geometry"),
            (["fill '#000', expected '#fff'"], "color"),
            (["stroke '#000', expected None"], "stroke"),
            (["text 'a', expected 'b'"], "text content"),
        ]:
            report = _report(_region("x", "mismatched", notes))
            result = triage_structural([report], systemic_threshold=1)
            assert expected_substring in (result.patterns[0].hint or "")

    def test_missing_pattern_carries_a_hint(self) -> None:
        report = _report(_region("x", "missing"))
        result = triage_structural([report], systemic_threshold=1)
        assert result.patterns[0].hint is not None
