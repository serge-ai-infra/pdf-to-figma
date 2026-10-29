"""IR contract tests — versioning, validation and the neutrality rules."""

from __future__ import annotations

import inspect
import io
import re
import tokenize

import pytest
from pydantic import ValidationError

import pdf2figma.extract.pdf as pdf_module
import pdf2figma.ir.model as ir_model
from pdf2figma.ir import IR_VERSION, BBox, Color, Document, IRVersionError, SourceInfo, load


class TestVersioning:
    def test_round_trip(self) -> None:
        document = Document(source=SourceInfo(page_count=0))
        assert load(document.model_dump(mode="json")).ir_version == IR_VERSION

    def test_foreign_version_is_refused(self) -> None:
        payload = Document(source=SourceInfo(page_count=0)).model_dump(mode="json")
        payload["ir_version"] = "99.0"
        with pytest.raises(IRVersionError, match=r"99\.0"):
            load(payload)

    def test_missing_version_is_refused(self) -> None:
        with pytest.raises(IRVersionError):
            load({"source": {"page_count": 0}, "pages": []})


class TestValidation:
    def test_color_must_be_lowercase_srgb_hex(self) -> None:
        assert Color(hex="#00ff7f").alpha == 1.0
        for bad in ("#FFF", "ff0000", "#GGGGGG", "#FF0000"):
            with pytest.raises(ValidationError):
                Color(hex=bad)

    def test_negative_extent_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            BBox(x=0, y=0, w=-1, h=10)

    def test_unknown_fields_are_refused(self) -> None:
        """Silently accepting extra keys would let stages drift apart unnoticed."""
        with pytest.raises(ValidationError):
            Color(hex="#000000", opacity=0.5)  # type: ignore[call-arg]


def _is_docstring(literal: str) -> bool:
    """Triple-quoted strings are prose; single-quoted ones are data in the code."""
    return literal.lstrip("rbuBRUF").startswith(('"""', "'''"))


class TestNeutrality:
    """The "no coupling" rule, made testable rather than aspirational."""

    MODULES = (ir_model, pdf_module)

    def test_no_hex_color_literals(self) -> None:
        # Format strings that build a hex value are fine; baked-in colors are not.
        literal = re.compile(r"[\"']#[0-9a-fA-F]{6}[\"']")
        for module in self.MODULES:
            assert not literal.search(inspect.getsource(module)), module.__name__

    def test_no_domain_vocabulary(self) -> None:
        """Checked against identifiers and literals, not prose.

        Comments discussing how a library "reports" a value are not domain
        coupling; a variable named `chart_type` is. Scanning raw source conflates
        the two and makes the rule unenforceable.
        """
        forbidden = (
            "chart", "donut", "pie", "kpi", "treemap", "dashboard", "widget",
            "revenue", "customer", "tenant", "invoice", "metric",
        )

        for module in self.MODULES:
            tokens = tokenize.generate_tokens(io.StringIO(inspect.getsource(module)).readline)
            meaningful = [
                token.string.lower()
                for token in tokens
                if token.type is tokenize.NAME
                or (token.type is tokenize.STRING and not _is_docstring(token.string))
            ]
            joined = " ".join(meaningful)
            for word in forbidden:
                assert not re.search(rf"\b{word}s?\b", joined), (
                    f"{module.__name__} uses {word!r} in code; "
                    "the engine must not know domain terms"
                )

    def test_no_network_access(self) -> None:
        for module in self.MODULES:
            source = inspect.getsource(module)
            for marker in ("requests", "urllib", "httpx", "socket"):
                assert marker not in source, module.__name__
