"""Repair triage — S5's deferred bookkeeping. Fixes nothing; see spec."""

from pdf2figma.repair.model import (
    REPAIR_VERSION,
    PerceptualRoundRegion,
    PerceptualRoundReport,
    RoundStatus,
    StructuralOccurrence,
    StructuralPattern,
    StructuralTriageReport,
    TriageClassification,
)
from pdf2figma.repair.perceptual import prepare_crops, track_rounds
from pdf2figma.repair.structural import triage_structural

__all__ = [
    "REPAIR_VERSION",
    "PerceptualRoundRegion",
    "PerceptualRoundReport",
    "RoundStatus",
    "StructuralOccurrence",
    "StructuralPattern",
    "StructuralTriageReport",
    "TriageClassification",
    "prepare_crops",
    "track_rounds",
    "triage_structural",
]
