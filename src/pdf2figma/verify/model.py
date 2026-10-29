"""What was actually built, and how it compares to the source.

`BuiltDocument` mirrors the plugin's export panel (`figma-plugin/src/code.ts`)
— the counterpart to the IR, in the other direction. `StructuralReport` and
`PerceptualReport` are this stage's two outputs; neither fixes anything, both
just say where source and built diverge. See `docs/specs/s5-verify/spec.md`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pdf2figma.ir import BBox

VERIFY_VERSION = "0.1"
"""Bumped on any breaking change to either report shape."""

BUILT_VERSION = "0.1"
"""The version the plugin's export panel stamps on `*.built.json`."""


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BuiltFont(Frozen):
    family: str
    size: float = Field(gt=0)
    weight: int | None = None
    italic: bool = False


class BuiltNode(Frozen):
    """One node the plugin actually built, read back off the live document.

    No `kind`, no `shape` — the plugin doesn't re-derive S1's classification,
    it just reports what it can read directly off the node (fill, stroke,
    text). Comparison against the source IR is `structural.py`'s job.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: str
    bbox: BBox
    fill: str | None = None
    # The plugin (figma-plugin/src/code.ts) is TS and serializes these
    # camelCase, matching its own BuiltNode interface — alias to accept that
    # JSON while keeping the snake_case attribute name every other Python
    # model in this codebase uses (inventory/model.py, extract/pdf.py, ...).
    stroke_color: str | None = Field(default=None, alias="strokeColor")
    stroke_width: float | None = Field(default=None, alias="strokeWidth")
    text: str | None = None
    font: BuiltFont | None = None


class BuiltPage(Frozen):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class BuiltDocument(Frozen):
    built_version: str
    page: BuiltPage
    nodes: list[BuiltNode] = Field(default_factory=list)


class BuiltVersionError(ValueError):
    """Raised when a built.json's version is not the one this build understands."""


def load_built(data: dict[str, object]) -> BuiltDocument:
    """Parse a built.json, refusing a version this build does not understand."""
    version = data.get("built_version")
    if version != BUILT_VERSION:
        raise BuiltVersionError(
            f"built.json version {version!r} cannot be read by this build "
            f"(expects {BUILT_VERSION!r}). Re-export from the plugin rather than migrating."
        )
    return BuiltDocument.model_validate(data)


RegionStatus = Literal["matched", "mismatched", "missing", "extra"]


class StructuralTolerances(Frozen):
    bbox: float = Field(ge=0)


class StructuralCounts(Frozen):
    matched: int = Field(ge=0)
    mismatched: int = Field(ge=0)
    missing: int = Field(ge=0)
    extra: int = Field(ge=0)


class StructuralRegion(Frozen):
    id: str
    status: RegionStatus
    bbox_delta: float | None = Field(default=None, ge=0)
    notes: list[str] = Field(default_factory=list)


class StructuralReport(Frozen):
    verify_version: str = VERIFY_VERSION
    tolerances: StructuralTolerances
    counts: StructuralCounts
    regions: list[StructuralRegion] = Field(default_factory=list)


PerceptualStatus = Literal["compared", "degenerate", "out-of-bounds"]


class PerceptualOverall(Frozen):
    """Whole-image numbers, for continuity with S3's ceiling measurement.

    Secondary to the per-region results below — see spec's non-goals.
    """

    mae: float
    rmse: float
    max_delta: float
    differing_px: int = Field(ge=0)
    differing_pct: float
    match_pct: float
    rows_touched_pct: float
    cols_touched_pct: float


class PerceptualRegion(Frozen):
    id: str
    status: PerceptualStatus
    match_pct: float | None = None
    mae: float | None = None
    rmse: float | None = None
    max_delta: float | None = None
    note: str | None = None


class PerceptualReport(Frozen):
    verify_version: str = VERIFY_VERSION
    dpi: float = Field(gt=0)
    threshold: int = Field(ge=0, le=255)
    overall: PerceptualOverall
    regions: list[PerceptualRegion] = Field(default_factory=list)
