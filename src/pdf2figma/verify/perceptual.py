"""Per-pixel comparison, whole-image and per-region.

The whole-image core (`load_rgb`, `compare`, `write_diff_map`) moved here from
`scripts/compare-images.py`, which is now a thin CLI wrapper around it — same
behavior, now a tested library function instead of script-only logic. See
`docs/specs/s5-verify/spec.md` for why per-region is the point of this stage
and the whole-image number is secondary.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import numpy as np
from PIL import Image

from pdf2figma.ir import BBox, Node
from pdf2figma.verify.model import (
    PerceptualOverall,
    PerceptualRegion,
    PerceptualReport,
    PerceptualStatus,
)


def load_rgb(path: Path) -> np.ndarray:
    """Load as RGB over white — alpha differences are not visual differences."""
    img: Image.Image = Image.open(path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(canvas, img)
    return np.asarray(img.convert("RGB"), dtype=np.float64)


class CompareMetrics(TypedDict):
    mae: float
    rmse: float
    max_delta: float
    differing_px: int
    differing_pct: float
    match_pct: float
    rows_touched_pct: float
    cols_touched_pct: float


def compare(ref: np.ndarray, cand: np.ndarray, threshold: int) -> CompareMetrics:
    delta = np.abs(ref - cand)
    per_pixel = delta.max(axis=2)

    differing = per_pixel > threshold
    total = per_pixel.size

    # Where the differences sit, not just how many. A page that is uniformly
    # off by a hair and a page with one destroyed region can share a mean.
    rows = differing.any(axis=1).sum()
    cols = differing.any(axis=0).sum()

    return {
        "mae": float(delta.mean()),
        "rmse": float(np.sqrt((delta**2).mean())),
        "max_delta": float(per_pixel.max()),
        "differing_px": int(differing.sum()),
        "differing_pct": 100.0 * float(differing.sum()) / total,
        "match_pct": 100.0 * (1.0 - float(differing.sum()) / total),
        "rows_touched_pct": 100.0 * rows / differing.shape[0],
        "cols_touched_pct": 100.0 * cols / differing.shape[1],
    }


def write_diff_map(ref: np.ndarray, cand: np.ndarray, out: Path, gain: float) -> None:
    """Amplified difference map: faint discrepancies are the ones missed by eye."""
    delta = np.abs(ref - cand).max(axis=2)
    heat = np.clip(delta * gain, 0, 255)
    rgb = np.stack(
        [
            np.full_like(heat, 255) - heat,  # differences drain toward red
            np.full_like(heat, 255) - heat,
            np.full_like(heat, 255) - heat * 0.35,
        ],
        axis=2,
    )
    Image.fromarray(rgb.astype(np.uint8)).save(out)


@dataclass(frozen=True)
class RegionCrop:
    array: np.ndarray | None
    status: PerceptualStatus
    note: str | None = None


def crop_region(img: np.ndarray, bbox: BBox, dpi: float) -> RegionCrop:
    """Points to pixels at `dpi/72` — the ratio S3 measured makes a
    `pdftoppm` reference and a Figma export comparable without resampling.
    """
    scale = dpi / 72.0
    x0, y0 = round(bbox.x * scale), round(bbox.y * scale)
    w, h = round(bbox.w * scale), round(bbox.h * scale)

    if w <= 0 or h <= 0:
        note = f"zero-area bbox ({bbox.w}x{bbox.h}pt)"
        return RegionCrop(array=None, status="degenerate", note=note)

    height, width = img.shape[0], img.shape[1]
    x1, y1 = x0 + w, y0 + h
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
        return RegionCrop(
            array=None,
            status="out-of-bounds",
            note=f"region [{x0},{y0},{x1},{y1}]px outside image {width}x{height}px",
        )

    return RegionCrop(array=img[y0:y1, x0:x1], status="compared")


def diff_perceptual(
    reference: np.ndarray,
    candidate: np.ndarray,
    source_nodes: Sequence[Node],
    dpi: float,
    threshold: int,
) -> PerceptualReport:
    overall = PerceptualOverall(**compare(reference, candidate, threshold))
    regions: list[PerceptualRegion] = []

    for node in source_nodes:
        ref_crop = crop_region(reference, node.bbox, dpi)
        if ref_crop.status != "compared" or ref_crop.array is None:
            regions.append(PerceptualRegion(id=node.id, status=ref_crop.status, note=ref_crop.note))
            continue

        cand_crop = crop_region(candidate, node.bbox, dpi)
        if cand_crop.status != "compared" or cand_crop.array is None:
            region = PerceptualRegion(id=node.id, status=cand_crop.status, note=cand_crop.note)
            regions.append(region)
            continue

        metrics = compare(ref_crop.array, cand_crop.array, threshold)
        regions.append(
            PerceptualRegion(
                id=node.id,
                status="compared",
                match_pct=metrics["match_pct"],
                mae=metrics["mae"],
                rmse=metrics["rmse"],
                max_delta=metrics["max_delta"],
            )
        )

    return PerceptualReport(dpi=dpi, threshold=threshold, overall=overall, regions=regions)
