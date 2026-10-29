"""The donor artifact — sibling to `Payload`/`BuiltDocument`, not a variant of
either. Versioned the same way every other cross-language artifact in this
project is, so a schema mismatch on the plugin side is an error, never a
silent guess.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from pdf2figma.ir import BBox

CONVERT_VERSION = "0.1"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DonorNode(Frozen):
    id: str
    bbox: BBox
    """Points, matching the source IR — the plugin, not this module, converts
    to px. Same boundary S4's payload draws, just on the other side of it."""
    svg: str


class DonorSet(Frozen):
    convert_version: str = CONVERT_VERSION
    nodes: list[DonorNode]
