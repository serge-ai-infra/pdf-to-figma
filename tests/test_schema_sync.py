"""Field-name drift between the three hand-maintained copies of one shape.

`PayloadNode` is duplicated between `emitter/src/payload.ts` and
`figma-plugin/src/code.ts` *by design* — two independent TypeScript module
systems, "keep the two in sync by hand" per the plugin file's own comment.
`BuiltNode`/`BuiltFont` cross the TypeScript/Python line entirely, with no
shared type at all. The real bug this guards against already happened once:
Python's `BuiltNode.stroke_color`/`stroke_width` didn't match the plugin's
serialized `strokeColor`/`strokeWidth` until a pydantic `alias` fixed it.

No TypeScript AST here — a depth-aware brace/semicolon walk is exact for
these three interfaces (flat, hand-written, no generics), matching
`test_privacy.py`'s own precedent of a regex source-scan over a parser for a
small, stable pattern. It would get confidently wrong on anything nested
more cleverly than a single inline object type (`font?: { ... }`), which is
exactly the one case handled explicitly below — everything else these
interfaces contain is a plain `name: Type;`/`name?: Type;` statement.
"""

from __future__ import annotations

import re
from pathlib import Path

from pdf2figma.verify.model import BuiltFont, BuiltNode

REPO_ROOT = Path(__file__).resolve().parent.parent
EMITTER_PAYLOAD_TS = REPO_ROOT / "emitter" / "src" / "payload.ts"
PLUGIN_CODE_TS = REPO_ROOT / "figma-plugin" / "src" / "code.ts"

_FIELD_RE = re.compile(r"^\s*(\w+)\??\s*:")


def _interface_body(source: str, name: str) -> str:
    """The text strictly between an `interface Name {`'s braces, matched by
    depth rather than by the first `}` — `PayloadNode.font` is itself an
    inline object type with its own braces and semicolons."""
    opening = re.search(rf"\binterface\s+{re.escape(name)}\s*{{", source)
    assert opening, f"no `interface {name}` found"

    depth = 1
    i = opening.end()
    while depth > 0:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    return source[opening.end() : i - 1]


def _top_level_statements(body: str) -> list[str]:
    """Split on `;` at brace depth 0 only, so a nested inline type's own
    `;`-separated fields never get mistaken for the outer interface's own."""
    statements: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in body:
        if ch in "{(<":
            depth += 1
        elif ch in "})>":
            depth -= 1
        if ch == ";" and depth == 0:
            statements.append("".join(current))
            current = []
        else:
            current.append(ch)
    if "".join(current).strip():
        statements.append("".join(current))
    return statements


def _interface_fields(source: str, name: str) -> set[str]:
    body = _interface_body(source, name)
    fields = set()
    for statement in _top_level_statements(body):
        match = _FIELD_RE.match(statement)
        if match:
            fields.add(match.group(1))
    assert fields, f"interface {name} yielded no fields — parser likely broken"
    return fields


def _python_json_fields(model: type) -> set[str]:
    """Each field's effective JSON key: its pydantic `alias` if it has one
    (the `BuiltNode.stroke_color` case), else the attribute name as-is."""
    return {field.alias or name for name, field in model.model_fields.items()}


class TestPayloadNodeStaysInSyncAcrossBothCopies:
    def test_same_field_names_in_emitter_and_plugin(self) -> None:
        emitter_fields = _interface_fields(EMITTER_PAYLOAD_TS.read_text(), "PayloadNode")
        plugin_fields = _interface_fields(PLUGIN_CODE_TS.read_text(), "PayloadNode")
        assert emitter_fields == plugin_fields


class TestBuiltNodeStaysInSyncBetweenPluginAndPython:
    def test_same_field_names_as_the_python_model(self) -> None:
        plugin_fields = _interface_fields(PLUGIN_CODE_TS.read_text(), "BuiltNode")
        python_fields = _python_json_fields(BuiltNode)
        assert plugin_fields == python_fields


class TestFontShapesStayInSync:
    def test_payload_font_matches_built_font(self) -> None:
        # Same risk, same fix shape, cheap to check now that the machinery
        # exists — payload.ts's PayloadFont is a separate named interface;
        # its inline copy inside PayloadNode is checked implicitly by the
        # PayloadNode-vs-PayloadNode test above (both sides use the same
        # inline shape or this test's sibling would already have failed).
        plugin_fields = _interface_fields(PLUGIN_CODE_TS.read_text(), "PayloadFont")
        python_fields = _python_json_fields(BuiltFont)
        assert plugin_fields == python_fields


class TestParserItself:
    """The parser is the risky part of this file — worth pinning directly,
    not just trusting it via the real interfaces it happens to get right."""

    def test_inline_nested_object_fields_are_not_mistaken_for_outer_fields(self) -> None:
        source = "interface Foo {\n  id: string;\n  font?: { family: string; size: number };\n}\n"
        assert _interface_fields(source, "Foo") == {"id", "font"}

    def test_optional_marker_is_stripped_from_the_field_name(self) -> None:
        source = "interface Foo {\n  fill?: string;\n}\n"
        assert _interface_fields(source, "Foo") == {"fill"}
