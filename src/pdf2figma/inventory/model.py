"""The inventory: what recurs across a corpus, how often, and what it costs to unify.

A separate artifact from the IR, with its own version. It reports tokens
(palette, type scale, spacing) and atom candidates (recurring shapes, recurring
text styles) — never multi-node composites, never a Figma node. See
`docs/specs/s2-tokens-inventory/spec.md` for the reasoning behind each cut.

Every clustering tolerance that shaped this report is carried in `tolerances`,
so the file is self-describing without the command line that produced it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pdf2figma.ir import ShapeKind

INVENTORY_VERSION = "0.1"
"""Bumped on any breaking change. A mismatch is an error, never a silent migration."""


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Tolerances(Frozen):
    """The knobs that decided every cluster in this report. Never a hidden guess."""

    color: float = Field(ge=0)
    size: float = Field(ge=0, description="Font size, shape width/height, stroke width.")
    spacing: float = Field(ge=0)
    min_occurrences: int = Field(ge=1)


class CorpusStats(Frozen):
    documents: int = Field(ge=0)
    pages: int = Field(ge=0)
    nodes: int = Field(ge=0)


class Occurrence(Frozen):
    """Where one instance of a candidate was found.

    `document` is an index into the input file list, never a path or filename —
    the same privacy property the IR itself has.
    """

    document: int = Field(ge=0)
    page: int = Field(ge=0)
    node_id: str


Role = Literal["fill", "stroke", "text"]


class ColorToken(Frozen):
    hex: str = Field(pattern=r"^#[0-9a-f]{6}$")
    count: int = Field(ge=1)
    max_delta: float = Field(ge=0, description="Farthest member from this cluster's centroid.")
    roles: dict[Role, int] = Field(default_factory=dict)


class SizeToken(Frozen):
    """One step of the type scale: a font size clustered within one (family, weight, italic)."""

    family: str
    weight: int | None = None
    italic: bool = False
    size: float = Field(gt=0)
    count: int = Field(ge=1)
    max_delta: float = Field(ge=0)


class SpacingToken(Frozen):
    axis: Literal["x", "y"]
    gap: float = Field(ge=0)
    count: int = Field(ge=1)
    max_delta: float = Field(ge=0)


class ShapeCandidate(Frozen):
    id: str
    shape: ShapeKind
    fill: str | None = None
    stroke_color: str | None = None
    stroke_width: float | None = None
    width: float = Field(ge=0)  # a line's bbox is legitimately 0 along one axis
    height: float = Field(ge=0)
    count: int = Field(ge=1)
    documents: int = Field(ge=1)
    presence_ratio: float = Field(ge=0, le=1)
    variant: bool
    max_size_delta: float = Field(ge=0)
    occurrences: list[Occurrence] = Field(default_factory=list)


class TextCandidate(Frozen):
    id: str
    family: str
    weight: int | None = None
    italic: bool = False
    size: float = Field(gt=0)
    color: str | None = None
    count: int = Field(ge=1)
    documents: int = Field(ge=1)
    presence_ratio: float = Field(ge=0, le=1)
    variant: bool
    sample_texts: list[str] = Field(default_factory=list)
    occurrences: list[Occurrence] = Field(default_factory=list)


class Inventory(Frozen):
    inventory_version: str = INVENTORY_VERSION
    corpus: CorpusStats
    tolerances: Tolerances
    palette: list[ColorToken] = Field(default_factory=list)
    type_scale: list[SizeToken] = Field(default_factory=list)
    spacing: list[SpacingToken] = Field(default_factory=list)
    shape_candidates: list[ShapeCandidate] = Field(default_factory=list)
    text_candidates: list[TextCandidate] = Field(default_factory=list)
    unclustered_shapes: int = Field(default=0, ge=0)
    unclustered_text: int = Field(default=0, ge=0)


class InventoryVersionError(ValueError):
    """Raised when a report's inventory version is not the one this build understands."""


def load(data: dict[str, object]) -> Inventory:
    """Parse an inventory report, refusing a version this build does not understand."""
    version = data.get("inventory_version")
    if version != INVENTORY_VERSION:
        raise InventoryVersionError(
            f"Inventory version {version!r} cannot be read by this build "
            f"(expects {INVENTORY_VERSION!r}). Re-run `inventory` rather than migrating the file."
        )
    return Inventory.model_validate(data)
