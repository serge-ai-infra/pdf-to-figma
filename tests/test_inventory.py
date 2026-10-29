"""Inventory contract tests — versioning, privacy and the neutrality rules.

Same obligations as the IR (`test_ir.py`, `test_privacy.py`), scoped to the new
`inventory` package rather than folded into those IR-specific files.
"""

from __future__ import annotations

import inspect
import io
import re
import tokenize

import pytest
from pydantic import ValidationError

import pdf2figma.inventory.build as build_module
import pdf2figma.inventory.candidates as candidates_module
import pdf2figma.inventory.cluster as cluster_module
import pdf2figma.inventory.model as inventory_model
import pdf2figma.inventory.tokens as tokens_module
from pdf2figma.inventory import (
    INVENTORY_VERSION,
    CorpusStats,
    Inventory,
    InventoryVersionError,
    Tolerances,
)
from pdf2figma.inventory import load as load_inventory
from pdf2figma.inventory.build import build_inventory
from tests.fixtures import synthetic_ir as fx

MODULES = (build_module, candidates_module, cluster_module, inventory_model, tokens_module)

_DEFAULT_TOLERANCES = Tolerances(color=6.0, size=0.5, spacing=1.0, min_occurrences=2)


def _empty_report() -> Inventory:
    corpus = CorpusStats(documents=0, pages=0, nodes=0)
    return Inventory(corpus=corpus, tolerances=_DEFAULT_TOLERANCES)


class TestVersioning:
    def test_round_trip(self) -> None:
        report = _empty_report()
        assert load_inventory(report.model_dump(mode="json")).inventory_version == INVENTORY_VERSION

    def test_foreign_version_is_refused(self) -> None:
        payload = _empty_report().model_dump(mode="json")
        payload["inventory_version"] = "99.0"
        with pytest.raises(InventoryVersionError, match=r"99\.0"):
            load_inventory(payload)

    def test_missing_version_is_refused(self) -> None:
        with pytest.raises(InventoryVersionError):
            load_inventory({"corpus": {"documents": 0, "pages": 0, "nodes": 0}})


class TestValidation:
    def test_unknown_fields_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            CorpusStats(documents=0, pages=0, nodes=0, extra_field=1)  # type: ignore[call-arg]


class TestBuildInventory:
    def test_tolerances_are_echoed_back(self) -> None:
        tolerances = Tolerances(color=1.0, size=2.0, spacing=3.0, min_occurrences=4)
        report = build_inventory(fx.card_corpus(), tolerances)
        assert report.tolerances == tolerances

    def test_corpus_stats_match_the_actual_input(self) -> None:
        documents = fx.card_corpus()
        report = build_inventory(documents, _DEFAULT_TOLERANCES)
        assert report.corpus.documents == len(documents)
        assert report.corpus.pages == sum(len(d.pages) for d in documents)
        assert report.corpus.nodes == sum(d.node_count() for d in documents)


def _is_docstring(literal: str) -> bool:
    return literal.lstrip("rbuBRUF").startswith(('"""', "'''"))


class TestNeutrality:
    """The "no coupling" rule, made testable rather than aspirational."""

    def test_no_hex_color_literals(self) -> None:
        literal = re.compile(r"[\"']#[0-9a-fA-F]{6}[\"']")
        for module in MODULES:
            assert not literal.search(inspect.getsource(module)), module.__name__

    def test_no_domain_vocabulary(self) -> None:
        forbidden = (
            "chart", "donut", "pie", "kpi", "treemap", "dashboard", "widget",
            "revenue", "customer", "tenant", "invoice", "metric",
        )
        for module in MODULES:
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
                    f"{module.__name__} uses {word!r}; the engine must not know domain terms"
                )

    def test_no_network_access(self) -> None:
        for module in MODULES:
            source = inspect.getsource(module)
            for marker in ("requests", "urllib", "httpx", "socket"):
                assert marker not in source, module.__name__

    def test_no_filesystem_access(self) -> None:
        """Only the CLI does I/O — this is what keeps that guarantee structural."""
        builtin_open = re.compile(r"(?<![\w.])open\s*\(")
        for module in MODULES:
            source = inspect.getsource(module)
            assert not builtin_open.search(source), f"{module.__name__} opens a file directly"
            assert "pathlib" not in source, module.__name__


PATH_PATTERN = re.compile(r"(/Users/|/home/|[A-Za-z]:\\\\|\.ir\.json\b)", re.IGNORECASE)


class TestPrivacy:
    def test_occurrence_has_no_path_or_filename_field(self) -> None:
        fields = set(inventory_model.Occurrence.model_fields)
        assert not fields & {"path", "filename", "file", "source_path", "name"}
        assert fields == {"document", "page", "node_id"}

    def test_report_output_contains_no_filesystem_path(self) -> None:
        report = build_inventory(fx.card_corpus(), _DEFAULT_TOLERANCES)
        payload = report.model_dump(mode="json")
        assert not PATH_PATTERN.search(str(payload))

    def test_occurrence_document_is_an_index_not_a_path(self) -> None:
        report = build_inventory(fx.card_corpus(), _DEFAULT_TOLERANCES)
        for candidate in report.shape_candidates + report.text_candidates:
            for occurrence in candidate.occurrences:
                assert isinstance(occurrence.document, int)
                assert 0 <= occurrence.document < len(fx.card_corpus())
