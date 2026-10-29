"""Round-over-round tracking, and the crops a hypothesis-writing step needs.

Neither function writes a hypothesis. `track_rounds` only has a slot to
receive one (`--hypotheses`, wired in `cli.py`); `prepare_crops` only saves
the three images `architecture.md` says that step needs. See spec's
"Non-goals" for why generating one isn't this module's job.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from pdf2figma.ir import Node
from pdf2figma.repair.model import PerceptualRoundRegion, PerceptualRoundReport, RoundStatus
from pdf2figma.verify import PerceptualReport, crop_region, write_diff_map


def track_rounds(
    previous: PerceptualRoundReport | None,
    current: PerceptualReport,
    threshold: float,
    needs_human_after: int,
    hypotheses: Mapping[str, str] | None = None,
) -> PerceptualRoundReport:
    """Compare the current round against the previous one, region by region.

    Only regions currently below `threshold` are tracked — one that has
    climbed back above it simply stops appearing; its full history is still
    in the underlying perceptual reports.
    """
    previous_by_id = {r.id: r for r in previous.regions} if previous else {}
    round_number = previous.round + 1 if previous else 1
    hint_overrides = hypotheses or {}

    regions: list[PerceptualRoundRegion] = []
    for region in current.regions:
        if region.status != "compared" or region.match_pct is None:
            continue
        if region.match_pct >= threshold:
            continue

        prior = previous_by_id.get(region.id)
        hypothesis = hint_overrides.get(region.id, prior.hypothesis if prior else None)

        if prior is None:
            regions.append(
                PerceptualRoundRegion(
                    id=region.id,
                    current_match_pct=region.match_pct,
                    status="new",
                    rounds_without_improvement=0,
                    hypothesis=hypothesis,
                )
            )
            continue

        delta = region.match_pct - prior.current_match_pct
        status: RoundStatus
        if delta > 0:
            status, rounds_without_improvement = "improved", 0
        else:
            rounds_without_improvement = prior.rounds_without_improvement + 1
            stalled = rounds_without_improvement >= needs_human_after
            status = "needs-human" if stalled else "tracking"

        regions.append(
            PerceptualRoundRegion(
                id=region.id,
                current_match_pct=region.match_pct,
                previous_match_pct=prior.current_match_pct,
                delta=delta,
                status=status,
                rounds_without_improvement=rounds_without_improvement,
                hypothesis=hypothesis,
            )
        )

    return PerceptualRoundReport(
        round=round_number,
        threshold=threshold,
        needs_human_after=needs_human_after,
        regions=regions,
    )


def prepare_crops(
    reference: np.ndarray,
    candidate: np.ndarray,
    source_nodes: Sequence[Node],
    ids: Sequence[str],
    dpi: float,
    out_dir: Path,
    gain: float = 4.0,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_id = {node.id: node for node in source_nodes}
    written: list[Path] = []

    for region_id in ids:
        node = by_id.get(region_id)
        if node is None:
            continue

        ref_crop = crop_region(reference, node.bbox, dpi)
        cand_crop = crop_region(candidate, node.bbox, dpi)
        if ref_crop.array is None or cand_crop.array is None:
            continue

        ref_path = out_dir / f"{region_id}.reference.png"
        cand_path = out_dir / f"{region_id}.candidate.png"
        diff_path = out_dir / f"{region_id}.diff.png"

        Image.fromarray(ref_crop.array.astype("uint8")).save(ref_path)
        Image.fromarray(cand_crop.array.astype("uint8")).save(cand_path)
        write_diff_map(ref_crop.array, cand_crop.array, diff_path, gain)

        written.extend([ref_path, cand_path, diff_path])

    return written
