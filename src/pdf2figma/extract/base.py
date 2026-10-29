"""Extraction interface.

Input is an interface rather than a PDF parser for a reason: a parsed document is
one source of an IR, and a layout specification from whatever generated the
document is another. A generator, where one is reachable, holds the same
information exactly — no inference, no tolerance. Both produce the same IR, and
everything downstream is indifferent to which was used.

Implementations take **bytes, not paths**. Core code performs no filesystem
access; only the CLI does I/O. That keeps tests free of fixtures on disk and makes
it structurally impossible for a path to leak into an artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pdf2figma.ir import Document


@dataclass(frozen=True)
class ExtractInput:
    data: bytes
    hint_mime: str | None = None


@dataclass(frozen=True)
class ExtractOptions:
    pages: tuple[int, ...] | None = None
    """Zero-based page indices; None means every page."""

    text_color: bool = True
    """Resolve per-character fill color. Off makes extraction faster and blinder."""

    run_gap_ratio: float = 0.35
    """Horizontal gap that splits a text run, as a fraction of font size.

    A parameter rather than a constant because grouping characters into runs is
    our inference, not the document's structure, and different documents space
    their glyphs differently.
    """

    warnings: list[str] = field(default_factory=list)
    """Populated during extraction; anything degraded is reported, not hidden."""


@runtime_checkable
class Extractor(Protocol):
    name: str

    def supports(self, inp: ExtractInput) -> bool: ...

    def extract(self, inp: ExtractInput, opts: ExtractOptions) -> Document: ...


class ExtractError(RuntimeError):
    """Raised when a document cannot be read at all — encrypted, corrupt, wrong type."""
