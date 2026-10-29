"""Privacy is asserted, not reviewed.

Extracts get attached to issues and pasted into chats. "We checked and it looked
fine" is not a guarantee; a test is. These also pin the structural decision that
makes the guarantee cheap: the extractor takes bytes, so there is no path for it
to record even if someone later wanted one.
"""

from __future__ import annotations

import inspect
import json
import re

import pdf2figma.convert.donor as donor_module
import pdf2figma.convert.poppler as poppler_module
import pdf2figma.extract.base as base
import pdf2figma.extract.pdf as pdf_module
import pdf2figma.ir.model as ir_model
from pdf2figma.extract import ExtractInput, ExtractOptions, PdfExtractor
from tests.fixtures import synthetic

PATH_PATTERN = re.compile(r"(/Users/|/home/|[A-Za-z]:\\\\|\.pdf\b)", re.IGNORECASE)


def extracted_json() -> str:
    document = PdfExtractor().extract(
        ExtractInput(data=synthetic.build_pdf(synthetic.RECT + " " + synthetic.TEXT)),
        ExtractOptions(),
    )
    return json.dumps(document.model_dump(mode="json"))


def test_output_contains_no_filesystem_path() -> None:
    assert not PATH_PATTERN.search(extracted_json())


def test_source_info_has_no_filename_field() -> None:
    """A field that does not exist cannot leak. Adding one should fail this test."""
    fields = set(ir_model.SourceInfo.model_fields)
    assert not fields & {"path", "filename", "file", "source_path", "name"}


def test_extract_input_carries_bytes_not_a_path() -> None:
    fields = {f.name for f in base.ExtractInput.__dataclass_fields__.values()}
    assert "data" in fields
    assert not fields & {"path", "filename"}


def test_core_modules_do_not_touch_the_filesystem() -> None:
    """Only the CLI does I/O. This is what keeps the guarantee structural.

    `convert.poppler` spawns a process rather than opening a file — bytes in
    over stdin, a string out over stdout, no path ever touches disk — so it
    holds to this same guarantee despite not being pure Python. See
    docs/specs/s3.5-geometry-donor/spec.md's boundary section.
    """
    # Bare `open(` only: `pdfplumber.open(` is preceded by a dot and
    # `_extract_open(` by a word character, so neither is a builtin file open.
    builtin_open = re.compile(r"(?<![\w.])open\s*\(")

    for module in (base, pdf_module, ir_model, donor_module, poppler_module):
        source = inspect.getsource(module)
        assert not builtin_open.search(source), (
            f"{module.__name__} opens a file directly; I/O belongs in cli.py"
        )
        assert "pathlib" not in source
