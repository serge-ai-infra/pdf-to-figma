"""What to do about a mismatch — grouped by pattern (structural), tracked
across rounds (perceptual). Neither report fixes anything; see
`docs/specs/s6-repair-triage/spec.md`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pdf2figma.verify import RegionStatus

REPAIR_VERSION = "0.1"
"""Bumped on any breaking change to either report shape."""


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


TriageClassification = Literal["systemic", "one-off"]


class StructuralOccurrence(Frozen):
    """Which input report a region came from, and its id there.

    Mirrors `pdf2figma.inventory.Occurrence` for the same reason: node ids
    like `p0.t5` repeat across different documents, so triaging several
    reports together needs to know which one each occurrence belongs to.
    """

    document: int = Field(ge=0)
    id: str


class StructuralPattern(Frozen):
    pattern_key: str
    status: RegionStatus
    count: int = Field(ge=1)
    classification: TriageClassification
    hint: str | None = None
    occurrences: list[StructuralOccurrence] = Field(default_factory=list)


class StructuralTriageReport(Frozen):
    repair_version: str = REPAIR_VERSION
    systemic_threshold: int = Field(ge=1)
    patterns: list[StructuralPattern] = Field(default_factory=list)


RoundStatus = Literal["new", "improved", "tracking", "needs-human"]
"""`tracking` covers both "unchanged" and "regressed" — the `delta` field
already carries that nuance; the status only needs to say whether the loop
should keep watching, stop (a human should look), or reset (it got better).
"""


class PerceptualRoundRegion(Frozen):
    id: str
    current_match_pct: float
    previous_match_pct: float | None = None
    delta: float | None = None
    status: RoundStatus
    rounds_without_improvement: int = Field(ge=0)
    hypothesis: str | None = None


class PerceptualRoundReport(Frozen):
    repair_version: str = REPAIR_VERSION
    round: int = Field(ge=1)
    threshold: float
    needs_human_after: int = Field(ge=1)
    regions: list[PerceptualRoundRegion] = Field(default_factory=list)
