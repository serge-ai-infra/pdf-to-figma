"""Command line entry point — the only place in the project that touches disk."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from pdf2figma.convert import ConvertError, DonorNode, DonorSet, crop_to_donor, page_to_svg
from pdf2figma.extract import ExtractError, ExtractInput, ExtractOptions, PdfExtractor
from pdf2figma.inventory import Tolerances, build_inventory
from pdf2figma.ir import IR_VERSION, BBox, Document, IRVersionError, ShapeNode
from pdf2figma.ir import load as ir_load
from pdf2figma.repair import PerceptualRoundReport, prepare_crops, track_rounds, triage_structural
from pdf2figma.verify import (
    BuiltVersionError,
    PerceptualReport,
    StructuralReport,
    StructuralTolerances,
    diff_perceptual,
    diff_structural,
    load_built,
    load_rgb,
)


def _parse_pages(spec: str) -> tuple[int, ...]:
    """Parse a 1-based page spec like `2-4,7` into zero-based indices."""
    indices: list[int] = []
    for part in spec.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, _, end_text = chunk.partition("-")
            start, end = int(start_text), int(end_text)
            if start < 1 or end < start:
                raise ValueError(f"invalid page range: {chunk!r}")
            indices.extend(range(start - 1, end))
        else:
            number = int(chunk)
            if number < 1:
                raise ValueError(f"page numbers start at 1: {chunk!r}")
            indices.append(number - 1)
    if not indices:
        raise ValueError("no pages selected")
    return tuple(sorted(set(indices)))


def _cmd_extract(args: argparse.Namespace) -> int:
    source: Path = args.input
    if not source.is_file():
        print(f"error: no such file: {source}", file=sys.stderr)
        return 1

    try:
        pages = _parse_pages(args.pages) if args.pages else None
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    options = ExtractOptions(pages=pages, text_color=not args.no_text_color)

    try:
        document = PdfExtractor().extract(ExtractInput(data=source.read_bytes()), options)
    except ExtractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for warning in options.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    payload = document.model_dump(mode="json", exclude_none=True)
    text = json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(
            f"{document.node_count()} nodes across {len(document.pages)} page(s) → {args.output}",
            file=sys.stderr,
        )
    else:
        print(text)

    return 0


def _cmd_inventory(args: argparse.Namespace) -> int:
    documents: list[Document] = []
    for source in args.inputs:
        if not source.is_file():
            print(f"error: no such file: {source}", file=sys.stderr)
            return 1
        try:
            documents.append(ir_load(json.loads(source.read_text(encoding="utf-8"))))
        except json.JSONDecodeError as exc:
            print(f"error: {source}: not valid JSON ({exc})", file=sys.stderr)
            return 2
        except IRVersionError as exc:
            print(f"error: {source}: {exc}", file=sys.stderr)
            return 2

    tolerances = Tolerances(
        color=args.color_tolerance,
        size=args.size_tolerance,
        spacing=args.spacing_tolerance,
        min_occurrences=args.min_occurrences,
    )
    report = build_inventory(documents, tolerances)

    payload = report.model_dump(mode="json", exclude_none=True)
    text = json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(
            f"{len(report.palette)} colors, {len(report.type_scale)} sizes, "
            f"{len(report.shape_candidates)} shape / {len(report.text_candidates)} text "
            f"candidates across {report.corpus.documents} document(s) → {args.output}",
            file=sys.stderr,
        )
    else:
        print(text)

    return 0


def _cmd_convert_donor(args: argparse.Namespace) -> int:
    pdf_path: Path = args.pdf
    if not pdf_path.is_file():
        print(f"error: no such file: {pdf_path}", file=sys.stderr)
        return 1

    document = _load_ir_page(args.ir, args.page)
    if isinstance(document, int):
        return document

    page_nodes = document.pages[args.page - 1].nodes

    if args.ids:
        ids = [part.strip() for part in args.ids.split(",") if part.strip()]
        if not ids:
            print("error: --ids must name at least one region", file=sys.stderr)
            return 1
    else:
        # No curated list — every path-kind node on the page. Hand-picking
        # ids doesn't scale once a real report turns out to have well over a
        # hundred of them (rounded bars, donuts, section headers are all
        # curves to a PDF, all `path` to S1's classifier); --ids stays for
        # the scoped/ad-hoc case, not as the only way in.
        ids = [n.id for n in page_nodes if isinstance(n, ShapeNode) and n.shape == "path"]
        if not ids:
            print(f"error: no path-kind shape nodes on page {args.page}", file=sys.stderr)
            return 1

    nodes_by_id = {node.id: node for node in page_nodes}
    bboxes: dict[str, BBox] = {}
    for node_id in ids:
        node = nodes_by_id.get(node_id)
        if node is None:
            print(f"error: no node {node_id!r} on page {args.page}", file=sys.stderr)
            return 2
        if not isinstance(node, ShapeNode) or node.shape != "path":
            print(
                f"error: {node_id!r} is not a path-kind shape node — "
                "donor import is only for the shapes S1 leaves geometry-less",
                file=sys.stderr,
            )
            return 2
        bboxes[node_id] = node.bbox

    try:
        page_svg = page_to_svg(pdf_path.read_bytes(), args.page)
        donors = [
            DonorNode(
                id=node_id, bbox=bboxes[node_id], svg=crop_to_donor(page_svg, bboxes[node_id])
            )
            for node_id in ids
        ]
    except ConvertError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = DonorSet(nodes=donors)

    payload = result.model_dump(mode="json", exclude_none=True)
    text = json.dumps(payload, indent=2 if args.pretty else None)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"{len(donors)} donor(s) → {args.output}", file=sys.stderr)
    else:
        print(text)

    return 0


def _load_ir_page(ir_path: Path, page: int) -> Document | int:
    """Returns the loaded document, or an exit code on failure."""
    if not ir_path.is_file():
        print(f"error: no such file: {ir_path}", file=sys.stderr)
        return 1
    try:
        document = ir_load(json.loads(ir_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, IRVersionError) as exc:
        print(f"error: {ir_path}: {exc}", file=sys.stderr)
        return 2
    if page < 1 or page > len(document.pages):
        print(f"error: page {page} does not exist ({len(document.pages)} page(s))", file=sys.stderr)
        return 2
    return document


def _cmd_verify_structural(args: argparse.Namespace) -> int:
    document = _load_ir_page(args.ir, args.page)
    if isinstance(document, int):
        return document

    built_path: Path = args.built
    if not built_path.is_file():
        print(f"error: no such file: {built_path}", file=sys.stderr)
        return 1
    try:
        built = load_built(json.loads(built_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, BuiltVersionError) as exc:
        print(f"error: {built_path}: {exc}", file=sys.stderr)
        return 2

    payload_data: dict[str, object] | None = None
    if args.payload:
        if not args.payload.is_file():
            print(f"error: no such file: {args.payload}", file=sys.stderr)
            return 1
        payload_data = json.loads(args.payload.read_text(encoding="utf-8"))

    tolerances = StructuralTolerances(bbox=args.bbox_tolerance)
    nodes = document.pages[args.page - 1].nodes
    report = diff_structural(nodes, built, tolerances, payload_data)

    payload = report.model_dump(mode="json", exclude_none=True)
    text = json.dumps(payload, indent=2 if args.pretty else None)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        c = report.counts
        print(
            f"{c.matched} matched, {c.mismatched} mismatched, {c.missing} missing, "
            f"{c.extra} extra → {args.output}",
            file=sys.stderr,
        )
    else:
        print(text)

    return 0


def _cmd_verify_perceptual(args: argparse.Namespace) -> int:
    document = _load_ir_page(args.ir, args.page)
    if isinstance(document, int):
        return document

    for path in (args.reference, args.candidate):
        if not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 1

    reference = load_rgb(args.reference)
    candidate = load_rgb(args.candidate)
    if reference.shape != candidate.shape:
        print(
            f"error: size mismatch — reference {reference.shape[1]}x{reference.shape[0]}, "
            f"candidate {candidate.shape[1]}x{candidate.shape[0]}. Export at the same dpi "
            "so both come out at the same pixel size; rescaling here would blur the "
            "differences being measured.",
            file=sys.stderr,
        )
        return 2

    nodes = document.pages[args.page - 1].nodes
    report = diff_perceptual(reference, candidate, nodes, args.dpi, args.threshold)

    payload = report.model_dump(mode="json", exclude_none=True)
    text = json.dumps(payload, indent=2 if args.pretty else None)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        compared = sum(1 for r in report.regions if r.status == "compared")
        print(
            f"{compared}/{len(report.regions)} region(s) compared, "
            f"overall {report.overall.match_pct:.2f}% match → {args.output}",
            file=sys.stderr,
        )
    else:
        print(text)

    return 0


def _cmd_repair_structural(args: argparse.Namespace) -> int:
    reports: list[StructuralReport] = []
    for source in args.inputs:
        if not source.is_file():
            print(f"error: no such file: {source}", file=sys.stderr)
            return 1
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            reports.append(StructuralReport.model_validate(data))
        except (json.JSONDecodeError, ValidationError) as exc:
            print(f"error: {source}: {exc}", file=sys.stderr)
            return 2

    result = triage_structural(reports, args.systemic_threshold)

    payload = result.model_dump(mode="json", exclude_none=True)
    text = json.dumps(payload, indent=2 if args.pretty else None)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        systemic = sum(1 for p in result.patterns if p.classification == "systemic")
        summary = f"{len(result.patterns)} pattern(s), {systemic} systemic → {args.output}"
        print(summary, file=sys.stderr)
    else:
        print(text)

    return 0


def _cmd_repair_perceptual_round(args: argparse.Namespace) -> int:
    current_path: Path = args.current
    if not current_path.is_file():
        print(f"error: no such file: {current_path}", file=sys.stderr)
        return 1
    try:
        current_data = json.loads(current_path.read_text(encoding="utf-8"))
        current = PerceptualReport.model_validate(current_data)
    except (json.JSONDecodeError, ValidationError) as exc:
        print(f"error: {current_path}: {exc}", file=sys.stderr)
        return 2

    previous: PerceptualRoundReport | None = None
    if args.previous:
        if not args.previous.is_file():
            print(f"error: no such file: {args.previous}", file=sys.stderr)
            return 1
        try:
            previous_data = json.loads(args.previous.read_text(encoding="utf-8"))
            previous = PerceptualRoundReport.model_validate(previous_data)
        except (json.JSONDecodeError, ValidationError) as exc:
            print(f"error: {args.previous}: {exc}", file=sys.stderr)
            return 2

    hypotheses: dict[str, str] | None = None
    if args.hypotheses:
        if not args.hypotheses.is_file():
            print(f"error: no such file: {args.hypotheses}", file=sys.stderr)
            return 1
        hypotheses = json.loads(args.hypotheses.read_text(encoding="utf-8"))

    result = track_rounds(previous, current, args.threshold, args.needs_human_after, hypotheses)

    payload = result.model_dump(mode="json", exclude_none=True)
    text = json.dumps(payload, indent=2 if args.pretty else None)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        needs_human = sum(1 for r in result.regions if r.status == "needs-human")
        print(
            f"round {result.round}: {len(result.regions)} region(s) below threshold, "
            f"{needs_human} needs-human → {args.output}",
            file=sys.stderr,
        )
    else:
        print(text)

    return 0


def _cmd_repair_crops(args: argparse.Namespace) -> int:
    document = _load_ir_page(args.ir, args.page)
    if isinstance(document, int):
        return document

    for path in (args.reference, args.candidate):
        if not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 1

    ids = [part.strip() for part in args.ids.split(",") if part.strip()]
    if not ids:
        print("error: --ids must name at least one region", file=sys.stderr)
        return 1

    reference = load_rgb(args.reference)
    candidate = load_rgb(args.candidate)
    nodes = document.pages[args.page - 1].nodes
    written = prepare_crops(reference, candidate, nodes, ids, args.dpi, args.output, args.gain)

    print(f"{len(written)} file(s) written to {args.output}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2figma",
        description="Rebuild a PDF as a componentized, verifiable Figma file.",
    )
    parser.add_argument("--version", action="version", version=f"IR {IR_VERSION}")

    subcommands = parser.add_subparsers(dest="command", required=True)

    extract = subcommands.add_parser(
        "extract",
        help="convert a PDF into the intermediate representation",
        description=(
            "Writes geometry, style and text as JSON. No interpretation: shapes are "
            "shapes, not charts. The output carries no path and no filename, so it "
            "can be shared without disclosing its source."
        ),
    )
    extract.add_argument("input", type=Path, help="source PDF")
    extract.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    extract.add_argument("--pages", help="1-based selection, e.g. '2-4,7'")
    extract.add_argument("--pretty", action="store_true", help="indent the JSON")
    extract.add_argument(
        "--no-text-color",
        action="store_true",
        help="skip per-character fill color (faster, blinder)",
    )
    extract.set_defaults(func=_cmd_extract)

    inventory = subcommands.add_parser(
        "inventory",
        help="cluster a corpus of extracted IR into tokens and recurring atoms",
        description=(
            "Reports a color palette, a type scale, a spacing grid, and recurring "
            "shape/text atoms across one or more *.ir.json files. Every clustering "
            "tolerance is a flag, echoed back in the report, never a hidden guess."
        ),
    )
    inventory.add_argument("inputs", nargs="+", type=Path, help="one or more *.ir.json files")
    inventory.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    inventory.add_argument("--pretty", action="store_true", help="indent the JSON")
    inventory.add_argument(
        "--color-tolerance",
        type=float,
        default=6.0,
        help="Euclidean sRGB distance within which two colors are the same token (default: 6.0)",
    )
    inventory.add_argument(
        "--size-tolerance",
        type=float,
        default=0.5,
        help="points within which font size / shape size / stroke width merge (default: 0.5)",
    )
    inventory.add_argument(
        "--spacing-tolerance",
        type=float,
        default=1.0,
        help="points within which two gaps are the same spacing token (default: 1.0)",
    )
    inventory.add_argument(
        "--min-occurrences",
        type=int,
        default=2,
        help="minimum recurrences before a cluster is reported as a candidate (default: 2)",
    )
    inventory.set_defaults(func=_cmd_inventory)

    convert = subcommands.add_parser(
        "convert",
        help="crop a PDF page's SVG conversion down to one region's geometry",
        description=(
            "Geometry-only, per region — see docs/specs/s3.5-geometry-donor/. "
            "Fixes nothing upstream: path-kind shapes stay unsupported in the "
            "payload; this hands the plugin their geometry through a separate panel."
        ),
    )
    convert_sub = convert.add_subparsers(dest="convert_command", required=True)

    convert_donor = convert_sub.add_parser(
        "donor",
        help="crop named path-kind regions into standalone donor SVGs",
    )
    convert_donor.add_argument("pdf", type=Path, help="source PDF")
    convert_donor.add_argument("ir", type=Path, help="source *.ir.json, for region bboxes")
    convert_donor.add_argument(
        "--ids",
        help="comma-separated path-kind shape node ids (default: every path-kind node on the page)",
    )
    convert_donor.add_argument("--page", type=int, default=1, help="1-based page (default: 1)")
    convert_donor.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    convert_donor.add_argument("--pretty", action="store_true", help="indent the JSON")
    convert_donor.set_defaults(func=_cmd_convert_donor)

    verify = subcommands.add_parser(
        "verify",
        help="compare a built Figma file back against its source, per node",
        description=(
            "Structural and perceptual comparison, per source-IR node. Reports where "
            "source and built diverge; fixes nothing — see docs/specs/s5-verify/."
        ),
    )
    verify_sub = verify.add_subparsers(dest="verify_command", required=True)

    structural = verify_sub.add_parser(
        "structural",
        help="exact per-node comparison: source IR vs. the plugin's built.json export",
    )
    structural.add_argument("ir", type=Path, help="source *.ir.json")
    structural.add_argument("built", type=Path, help="*.built.json from the plugin's export panel")
    structural.add_argument(
        "--payload", type=Path, help="optional payload.json to explain `missing` regions"
    )
    structural.add_argument("--page", type=int, default=1, help="1-based page (default: 1)")
    structural.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    structural.add_argument("--pretty", action="store_true", help="indent the JSON")
    structural.add_argument(
        "--bbox-tolerance",
        type=float,
        default=0.5,
        help="points within which a bbox counts as matching (default: 0.5)",
    )
    structural.set_defaults(func=_cmd_verify_structural)

    perceptual = verify_sub.add_parser(
        "perceptual",
        help="per-pixel comparison, cropped to each source-IR node's own region",
    )
    perceptual.add_argument("reference", type=Path, help="ground-truth render (e.g. pdftoppm)")
    perceptual.add_argument("candidate", type=Path, help="Figma-exported render")
    perceptual.add_argument("ir", type=Path, help="source *.ir.json, for region bboxes")
    perceptual.add_argument(
        "--dpi", type=float, required=True, help="dpi both images were rendered at"
    )
    perceptual.add_argument("--page", type=int, default=1, help="1-based page (default: 1)")
    perceptual.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    perceptual.add_argument("--pretty", action="store_true", help="indent the JSON")
    perceptual.add_argument(
        "--threshold",
        type=int,
        default=8,
        help="per-channel delta counted as a real difference (default: 8/255)",
    )
    perceptual.set_defaults(func=_cmd_verify_perceptual)

    repair = subcommands.add_parser(
        "repair",
        help="triage verification reports — pattern-groups mismatches, tracks rounds",
        description=(
            "Deterministic bookkeeping for S5's deferred repair loop. Fixes nothing — "
            "see docs/specs/s6-repair-triage/."
        ),
    )
    repair_sub = repair.add_subparsers(dest="repair_command", required=True)

    repair_structural = repair_sub.add_parser(
        "structural",
        help="group a structural report's mismatches by pattern; systemic vs one-off",
    )
    repair_structural.add_argument(
        "inputs", nargs="+", type=Path, help="one or more *.structural.json files"
    )
    repair_structural.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    repair_structural.add_argument("--pretty", action="store_true", help="indent the JSON")
    repair_structural.add_argument(
        "--systemic-threshold",
        type=int,
        default=2,
        help="regions sharing a pattern before it's called systemic (default: 2)",
    )
    repair_structural.set_defaults(func=_cmd_repair_structural)

    repair_round = repair_sub.add_parser(
        "perceptual-round",
        help="track a perceptual report's low scores across repeated runs",
    )
    repair_round.add_argument("current", type=Path, help="this run's *.perceptual.json")
    repair_round.add_argument("--previous", type=Path, help="the previous round's round report")
    repair_round.add_argument(
        "--hypotheses", type=Path, help='JSON {"region-id": "text"}, sets/overrides for this round'
    )
    repair_round.add_argument(
        "--threshold",
        type=float,
        default=95.0,
        help="match_pct below which a region is tracked (default: 95)",
    )
    repair_round.add_argument(
        "--needs-human-after",
        type=int,
        default=2,
        help="consecutive non-improving rounds before needs-human (default: 2)",
    )
    repair_round.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    repair_round.add_argument("--pretty", action="store_true", help="indent the JSON")
    repair_round.set_defaults(func=_cmd_repair_perceptual_round)

    repair_crops = repair_sub.add_parser(
        "crops",
        help="save reference/candidate/diff crops for a set of regions",
    )
    repair_crops.add_argument("reference", type=Path, help="ground-truth render")
    repair_crops.add_argument("candidate", type=Path, help="Figma-exported render")
    repair_crops.add_argument("ir", type=Path, help="source *.ir.json, for region bboxes")
    repair_crops.add_argument("--ids", required=True, help="comma-separated region ids")
    repair_crops.add_argument(
        "--dpi", type=float, required=True, help="dpi both images were rendered at"
    )
    repair_crops.add_argument("--page", type=int, default=1, help="1-based page (default: 1)")
    repair_crops.add_argument(
        "-o", "--output", type=Path, required=True, help="output directory"
    )
    repair_crops.add_argument(
        "--gain", type=float, default=4.0, help="difference map amplification"
    )
    repair_crops.set_defaults(func=_cmd_repair_crops)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
