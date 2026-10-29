"""Deterministic pattern-grouping.

`architecture.md` frames systemic-vs-one-off as an agent's job, but the
grouping key is syntactic — which field diverges and how — exactly what a
human reading the same notes would group by. No LLM call needed.
"""

from __future__ import annotations

from collections.abc import Sequence

from pdf2figma.repair.model import StructuralOccurrence, StructuralPattern, StructuralTriageReport
from pdf2figma.verify import RegionStatus, StructuralReport

_NOTE_KIND_PREFIXES: tuple[tuple[str, str], ...] = (
    ("bbox delta", "bbox"),
    ("fill", "fill"),
    ("stroke", "stroke"),
    ("text", "text"),
)

_HINTS: dict[str, str] = {
    "bbox": (
        "geometry mismatch — check the emitter's px/pt conversion or the "
        "plugin's resize/position calls"
    ),
    "fill": (
        "color mismatch — check candidate matching against the palette or "
        "the plugin's fill-reading"
    ),
    "stroke": (
        "stroke mismatch — check candidate matching against stroke "
        "tolerance or the plugin's stroke-reading"
    ),
    "text": "text content mismatch — check the live-text override logic",
}

_MISSING_HINT = (
    "no node built for this id — check whether it's an intentional S4 skip "
    "(unsupported kind, unloadable font) or a candidate-matching failure"
)
_EXTRA_HINT = (
    "built node with no matching source id — check whether built.json is "
    "stale or hand-edited"
)


def _note_kind(note: str) -> str:
    for prefix, kind in _NOTE_KIND_PREFIXES:
        if note.startswith(prefix):
            return kind
    return "other"


def _pattern_key(status: RegionStatus, notes: Sequence[str]) -> str:
    if status == "extra":
        return "extra"

    if status == "missing":
        if notes and notes[0].startswith("payload: "):
            reason = notes[0].removeprefix("payload: ").split(",")[0].split(" — ")[0].strip()
            return f"missing:{reason}"
        return "missing:no-context"

    kinds = sorted({_note_kind(n) for n in notes})
    return "mismatched:" + "+".join(kinds) if kinds else "mismatched:unknown"


def _hint_for(pattern_key: str) -> str | None:
    if pattern_key.startswith("missing"):
        return _MISSING_HINT
    if pattern_key == "extra":
        return _EXTRA_HINT
    if pattern_key.startswith("mismatched:"):
        kinds = pattern_key.removeprefix("mismatched:").split("+")
        matched = [_HINTS[kind] for kind in kinds if kind in _HINTS]
        if matched:
            return " / ".join(matched)
    return None


def triage_structural(
    reports: Sequence[StructuralReport], systemic_threshold: int = 2
) -> StructuralTriageReport:
    groups: dict[str, list[StructuralOccurrence]] = {}
    statuses: dict[str, RegionStatus] = {}

    for doc_index, report in enumerate(reports):
        for region in report.regions:
            if region.status == "matched":
                continue
            key = _pattern_key(region.status, region.notes)
            occurrence = StructuralOccurrence(document=doc_index, id=region.id)
            groups.setdefault(key, []).append(occurrence)
            statuses[key] = region.status

    ordered_keys = sorted(groups, key=lambda key: (-len(groups[key]), key))
    patterns = [
        StructuralPattern(
            pattern_key=key,
            status=statuses[key],
            count=len(groups[key]),
            classification="systemic" if len(groups[key]) >= systemic_threshold else "one-off",
            hint=_hint_for(key),
            occurrences=groups[key],
        )
        for key in ordered_keys
    ]

    return StructuralTriageReport(systemic_threshold=systemic_threshold, patterns=patterns)
