"""End-to-end `pdf2figma inventory`, via the real CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

from pdf2figma.cli import main
from pdf2figma.inventory import INVENTORY_VERSION
from pdf2figma.ir import IR_VERSION
from tests.fixtures import synthetic_ir as fx


def test_valid_corpus_produces_a_report(tmp_path: Path) -> None:
    documents = fx.card_corpus()
    paths = []
    for i, document in enumerate(documents):
        path = tmp_path / f"doc{i}.ir.json"
        path.write_text(json.dumps(document.model_dump(mode="json", exclude_none=True)))
        paths.append(path)

    out = tmp_path / "out.inventory.json"
    code = main(["inventory", *[str(p) for p in paths], "-o", str(out)])

    assert code == 0
    report = json.loads(out.read_text())
    assert report["inventory_version"] == INVENTORY_VERSION
    assert report["corpus"]["documents"] == 3
    assert len(report["palette"]) >= 1
    assert len(report["shape_candidates"]) >= 1


def test_missing_file_fails_clearly(tmp_path: Path) -> None:
    code = main(["inventory", str(tmp_path / "nope.ir.json")])
    assert code == 1


def test_version_mismatch_fails_clearly(tmp_path: Path) -> None:
    document = fx.card_corpus()[0]
    payload = document.model_dump(mode="json", exclude_none=True)
    payload["ir_version"] = "99.0"
    path = tmp_path / "bad.ir.json"
    path.write_text(json.dumps(payload))
    assert IR_VERSION != "99.0"

    code = main(["inventory", str(path)])
    assert code == 2


def test_color_tolerance_flag_changes_clustering(tmp_path: Path) -> None:
    close_colors = [fx.rect_node("a", 0, 0, 10, 10, fill="#000000")]
    doc_a = fx.document_of(fx.page_of(close_colors))
    doc_b = fx.document_of(fx.page_of([fx.rect_node("b", 0, 0, 10, 10, fill="#000005")]))

    path_a = tmp_path / "a.ir.json"
    path_b = tmp_path / "b.ir.json"
    path_a.write_text(json.dumps(doc_a.model_dump(mode="json", exclude_none=True)))
    path_b.write_text(json.dumps(doc_b.model_dump(mode="json", exclude_none=True)))

    tight = tmp_path / "tight.inventory.json"
    loose = tmp_path / "loose.inventory.json"
    main(["inventory", str(path_a), str(path_b), "-o", str(tight), "--color-tolerance", "0"])
    main(["inventory", str(path_a), str(path_b), "-o", str(loose), "--color-tolerance", "6"])

    tight_palette = json.loads(tight.read_text())["palette"]
    loose_palette = json.loads(loose.read_text())["palette"]
    assert len(tight_palette) == 2
    assert len(loose_palette) == 1
