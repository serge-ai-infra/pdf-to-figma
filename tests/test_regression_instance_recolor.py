"""Regression fixture for a real bug: a reused component instance kept its
master's fill/stroke instead of its own source node's (fixed in
`figma-plugin/src/code.ts`'s `applyInstanceStyle`). `code.ts` itself has no
headless test path — the `figma` global only exists inside a live plugin
sandbox — so this tests the *detector*:
if the bug ever comes back, does `verify.diff_structural` and
`repair.triage_structural` still catch it?

Deliberately doesn't model candidateId or masters at all. `verify` never
sees either — it compares a built node to its source node by id, nothing
more — so a fixture that tried to construct "two instances of one master"
would be modeling machinery this code doesn't touch. What matters is just:
two source nodes with different fills, and a built document where one of
them wrongly got the other's.
"""

from __future__ import annotations

from pdf2figma.repair import triage_structural
from pdf2figma.verify import (
    BUILT_VERSION,
    BuiltDocument,
    BuiltNode,
    BuiltPage,
    StructuralTolerances,
    diff_structural,
)
from tests.fixtures import synthetic_ir as fx

TOL = StructuralTolerances(bbox=0.5)

FIRST_FILL = "#3355ff"
SECOND_FILL = "#ff9900"


def _source() -> list[fx.ShapeNode]:
    # Same shape/size signature — the kind of pair S2 would cluster into one
    # candidate — but genuinely different fills, e.g. the same icon glyph
    # painted in two different accent colors (the real-world case
    # behind the fix).
    return [
        fx.rect_node("icon.0", 0, 0, 20, 20, fill=FIRST_FILL),
        fx.rect_node("icon.1", 100, 0, 20, 20, fill=SECOND_FILL),
    ]


def _built(*, buggy: bool) -> BuiltDocument:
    source = _source()
    page = BuiltPage(width=200, height=50)
    second_fill = FIRST_FILL if buggy else SECOND_FILL  # the bug: stuck on the first's color
    return BuiltDocument(
        built_version=BUILT_VERSION,
        page=page,
        nodes=[
            BuiltNode(id="icon.0", bbox=source[0].bbox, fill=FIRST_FILL),
            BuiltNode(id="icon.1", bbox=source[1].bbox, fill=second_fill),
        ],
    )


class TestFixedBehaviorIsMatched:
    def test_each_instance_reports_its_own_fill(self) -> None:
        report = diff_structural(_source(), _built(buggy=False), TOL)
        assert [r.status for r in report.regions] == ["matched", "matched"]


class TestRecolorBugIsCaught:
    def test_second_instance_wearing_the_first_s_fill_is_mismatched(self) -> None:
        report = diff_structural(_source(), _built(buggy=True), TOL)
        statuses = {r.id: r.status for r in report.regions}
        assert statuses["icon.0"] == "matched"
        assert statuses["icon.1"] == "mismatched"
        notes = next(r.notes for r in report.regions if r.id == "icon.1")
        assert notes == [f"fill '{FIRST_FILL}', expected '{SECOND_FILL}'"]

    def test_triage_groups_it_under_the_fill_pattern(self) -> None:
        report = diff_structural(_source(), _built(buggy=True), TOL)
        result = triage_structural([report], systemic_threshold=1)
        assert [p.pattern_key for p in result.patterns] == ["mismatched:fill"]
        assert result.patterns[0].count == 1
