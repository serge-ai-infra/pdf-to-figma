"""Round-over-round tracking against hand-built perceptual reports, and
`prepare_crops` against synthetic images.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pdf2figma.repair import track_rounds
from pdf2figma.repair.perceptual import prepare_crops
from pdf2figma.verify import PerceptualOverall, PerceptualRegion, PerceptualReport
from tests.fixtures import synthetic_ir as fx

THRESHOLD = 95.0
NEEDS_HUMAN_AFTER = 2

_OVERALL = PerceptualOverall(
    mae=0,
    rmse=0,
    max_delta=0,
    differing_px=0,
    differing_pct=0,
    match_pct=100,
    rows_touched_pct=0,
    cols_touched_pct=0,
)


def _report(*regions: PerceptualRegion) -> PerceptualReport:
    return PerceptualReport(dpi=72, threshold=8, overall=_OVERALL, regions=list(regions))


def _compared(id: str, match_pct: float) -> PerceptualRegion:
    return PerceptualRegion(
        id=id, status="compared", match_pct=match_pct, mae=0, rmse=0, max_delta=0
    )


class TestTrackRounds:
    def test_first_seen_region_is_new(self) -> None:
        result = track_rounds(None, _report(_compared("r1", 80)), THRESHOLD, NEEDS_HUMAN_AFTER)
        assert result.round == 1
        assert result.regions[0].status == "new"
        assert result.regions[0].rounds_without_improvement == 0

    def test_region_at_or_above_threshold_is_not_tracked(self) -> None:
        result = track_rounds(None, _report(_compared("r1", 99)), THRESHOLD, NEEDS_HUMAN_AFTER)
        assert result.regions == []

    def test_improving_region_resets_the_counter(self) -> None:
        round1 = track_rounds(None, _report(_compared("r1", 80)), THRESHOLD, NEEDS_HUMAN_AFTER)
        round2 = track_rounds(round1, _report(_compared("r1", 85)), THRESHOLD, NEEDS_HUMAN_AFTER)
        assert round2.regions[0].status == "improved"
        assert round2.regions[0].rounds_without_improvement == 0
        assert round2.regions[0].delta == pytest.approx(5.0)

    def test_two_non_improving_rounds_produce_needs_human(self) -> None:
        round1 = track_rounds(None, _report(_compared("r1", 80)), THRESHOLD, NEEDS_HUMAN_AFTER)
        round2 = track_rounds(round1, _report(_compared("r1", 80)), THRESHOLD, NEEDS_HUMAN_AFTER)
        round3 = track_rounds(round2, _report(_compared("r1", 79)), THRESHOLD, NEEDS_HUMAN_AFTER)

        assert round2.regions[0].status == "tracking"
        assert round2.regions[0].rounds_without_improvement == 1
        assert round3.regions[0].status == "needs-human"
        assert round3.regions[0].rounds_without_improvement == 2

    def test_region_climbing_back_above_threshold_drops_out(self) -> None:
        round1 = track_rounds(None, _report(_compared("r1", 80)), THRESHOLD, NEEDS_HUMAN_AFTER)
        round2 = track_rounds(round1, _report(_compared("r1", 97)), THRESHOLD, NEEDS_HUMAN_AFTER)
        assert round2.regions == []

    def test_hypotheses_override_the_current_round(self) -> None:
        round1 = track_rounds(None, _report(_compared("r1", 80)), THRESHOLD, NEEDS_HUMAN_AFTER)
        round2 = track_rounds(
            round1,
            _report(_compared("r1", 80)),
            THRESHOLD,
            NEEDS_HUMAN_AFTER,
            hypotheses={"r1": "donut segments start at 3 o'clock instead of 12"},
        )
        assert round2.regions[0].hypothesis == "donut segments start at 3 o'clock instead of 12"

    def test_hypothesis_carries_forward_without_a_new_one(self) -> None:
        round1 = track_rounds(
            None,
            _report(_compared("r1", 80)),
            THRESHOLD,
            NEEDS_HUMAN_AFTER,
            hypotheses={"r1": "shifted right"},
        )
        round2 = track_rounds(round1, _report(_compared("r1", 80)), THRESHOLD, NEEDS_HUMAN_AFTER)
        assert round2.regions[0].hypothesis == "shifted right"


class TestPrepareCrops:
    def test_writes_three_files_per_requested_id(self, tmp_path: Path) -> None:
        reference = np.full((100, 100, 3), 255.0)
        candidate = np.full((100, 100, 3), 255.0)
        nodes = [fx.rect_node("r1", 0, 0, 50, 50, fill="#3355ff")]

        written = prepare_crops(reference, candidate, nodes, ["r1"], dpi=72, out_dir=tmp_path)

        assert len(written) == 3
        assert (tmp_path / "r1.reference.png").is_file()
        assert (tmp_path / "r1.candidate.png").is_file()
        assert (tmp_path / "r1.diff.png").is_file()

    def test_unknown_id_is_skipped_not_crashed(self, tmp_path: Path) -> None:
        reference = np.full((100, 100, 3), 255.0)
        candidate = np.full((100, 100, 3), 255.0)

        written = prepare_crops(reference, candidate, [], ["nope"], dpi=72, out_dir=tmp_path)
        assert written == []
