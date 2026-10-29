"""The intermediate representation: geometry, style and text. No semantics.

Deliberately dumb. The IR knows about text runs, shapes and images — never about
charts, cards, or anything a reader would call the thing by. Interpretation
belongs to later stages, where it is driven by a profile the user supplies.

Two conventions are fixed here so nothing downstream has to think about them:

**Origin is top-left, y grows downward**, matching Figma and every renderer we
compare against. A PDF's bottom-up space is converted once, during extraction.

**Units are PDF points** (1/72"). Pixels and DPI appear only at render time, and
Figma's own unit — CSS pixels, where one point is 4/3px — is applied by the
emitter, not stored here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

IR_VERSION = "0.1"
"""Bumped on any breaking change. A mismatch is an error, never a silent migration."""


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BBox(Frozen):
    """Axis-aligned box in points, top-left origin."""

    x: float
    y: float
    w: float = Field(ge=0)
    h: float = Field(ge=0)

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return self.w * self.h


class Color(Frozen):
    """sRGB, `#rrggbb`, plus alpha.

    A source that is not sRGB is converted and flagged on the document, because
    the conversion is lossy and caps the accuracy any rebuild can reach.
    """

    hex: str = Field(pattern=r"^#[0-9a-f]{6}$")
    alpha: float = Field(default=1.0, ge=0.0, le=1.0)


class Stroke(Frozen):
    color: Color
    width: float = Field(ge=0)


class Font(Frozen):
    family: str
    size: float = Field(gt=0)
    weight: int | None = Field(default=None, ge=1, le=1000)
    italic: bool = False


Confidence = Literal["exact", "approx", "unknown"]
"""Uncertainty is recorded, never replaced by a plausible value."""


class NodeBase(Frozen):
    id: str
    bbox: BBox
    z: int = Field(ge=0, description="Painting order within the page; higher is later.")


class TextNode(NodeBase):
    kind: Literal["text"] = "text"
    text: str
    font: Font
    color: Color | None = None
    color_confidence: Confidence = "unknown"


ShapeKind = Literal["rect", "ellipse", "line", "path"]


class ShapeNode(NodeBase):
    """A drawn path, classified only by what its construction plainly shows.

    Ambiguous geometry resolves to `path`. Being vague is cheaper than being
    wrong: later stages cluster on these labels, so a mislabelled ellipse
    contaminates a whole component candidate.
    """

    kind: Literal["shape"] = "shape"
    shape: ShapeKind
    fill: Color | None = None
    stroke: Stroke | None = None
    closed: bool = True


class ImageNode(NodeBase):
    kind: Literal["image"] = "image"
    image_id: str
    mime: str | None = None


Node = Annotated[TextNode | ShapeNode | ImageNode, Field(discriminator="kind")]


class Page(Frozen):
    index: int = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    rotation: int = 0
    nodes: list[Node] = Field(default_factory=list)


class SourceInfo(Frozen):
    """What the document says about itself — never where it came from.

    No path and no filename by design. Extracts get attached to issues and pasted
    into chats; they must not disclose their origin.
    """

    page_count: int = Field(ge=0)
    producer: str | None = None
    creator: str | None = None
    title: str | None = None
    color_space: str | None = Field(
        default=None,
        description="Recorded when the source is not sRGB, since conversion caps accuracy.",
    )


class Document(Frozen):
    ir_version: str = IR_VERSION
    source: SourceInfo
    pages: list[Page] = Field(default_factory=list)

    def node_count(self) -> int:
        return sum(len(page.nodes) for page in self.pages)


class IRVersionError(ValueError):
    """Raised when a document's IR version is not the one this build understands."""


def load(data: dict[str, object]) -> Document:
    """Parse an IR document, refusing a version this build does not understand."""
    version = data.get("ir_version")
    if version != IR_VERSION:
        raise IRVersionError(
            f"IR version {version!r} cannot be read by this build (expects {IR_VERSION!r}). "
            "Re-extract the document rather than migrating the file."
        )
    return Document.model_validate(data)
