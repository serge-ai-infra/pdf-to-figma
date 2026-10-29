#!/usr/bin/env python3
"""One consolidated report: structural diff, optional perceptual diff, and
structural triage, plus a coarse verdict — `ok` or `needs-review`.

A convenience wrapper around `pdf2figma verify`/`pdf2figma repair`, for the
case where running three commands and reading three files is more ceremony
than the question deserves: did the build actually match the source?
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pdf2figma.ir import IRVersionError
from pdf2figma.ir import load as ir_load
from pdf2figma.repair import triage_structural
from pdf2figma.verify import (
    BuiltVersionError,
    StructuralTolerances,
    diff_perceptual,
    diff_structural,
    load_built,
    load_rgb,
)

_PERCEPTUAL_OK_THRESHOLD = 90.0
"""Below this overall match_pct, the verdict is `needs-review` even with no
structural problems — a coarse cutoff, not a calibrated ceiling like S3's."""


def _verdict(
    structural: dict[str, object], perceptual: dict[str, object] | None, systemic_patterns: int
) -> str:
    counts = structural["counts"]
    problems = (
        counts["mismatched"]  # type: ignore[index]
        or counts["extra"]  # type: ignore[index]
        or counts["missing"]  # type: ignore[index]
        or systemic_patterns
    )
    if problems:
        return "needs-review"
    if perceptual is not None:
        overall = perceptual["overall"]
        if overall["match_pct"] < _PERCEPTUAL_OK_THRESHOLD:  # type: ignore[index]
            return "needs-review"
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("ir", type=Path, help="source *.ir.json")
    ap.add_argument("built", type=Path, help="*.built.json from the plugin's export panel")
    ap.add_argument(
        "--payload", type=Path, help="optional payload.json, explains `missing` regions"
    )
    ap.add_argument("--page", type=int, default=1, help="1-based page (default: 1)")
    ap.add_argument("--bbox-tolerance", type=float, default=0.5)
    ap.add_argument("--reference", type=Path, help="reference PNG, for the perceptual half")
    ap.add_argument("--candidate", type=Path, help="Figma-exported PNG, for the perceptual half")
    ap.add_argument(
        "--dpi", type=float, help="dpi both PNGs were rendered at (required with --reference)"
    )
    ap.add_argument("--systemic-threshold", type=int, default=2)
    ap.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    for path in (args.ir, args.built):
        if not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 1

    try:
        document = ir_load(json.loads(args.ir.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, IRVersionError) as exc:
        print(f"error: {args.ir}: {exc}", file=sys.stderr)
        return 2

    if args.page < 1 or args.page > len(document.pages):
        pages = len(document.pages)
        print(f"error: page {args.page} does not exist ({pages} page(s))", file=sys.stderr)
        return 2
    nodes = document.pages[args.page - 1].nodes

    try:
        built = load_built(json.loads(args.built.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, BuiltVersionError) as exc:
        print(f"error: {args.built}: {exc}", file=sys.stderr)
        return 2

    payload_data: dict[str, object] | None = None
    if args.payload:
        if not args.payload.is_file():
            print(f"error: no such file: {args.payload}", file=sys.stderr)
            return 1
        payload_data = json.loads(args.payload.read_text(encoding="utf-8"))

    tolerances = StructuralTolerances(bbox=args.bbox_tolerance)
    structural_report = diff_structural(nodes, built, tolerances, payload_data)
    triage = triage_structural([structural_report], args.systemic_threshold)

    perceptual_dict: dict[str, object] | None = None
    if args.reference or args.candidate:
        if not (args.reference and args.candidate and args.dpi):
            print("error: --reference/--candidate/--dpi must be given together", file=sys.stderr)
            return 1
        for path in (args.reference, args.candidate):
            if not path.is_file():
                print(f"error: no such file: {path}", file=sys.stderr)
                return 1
        reference = load_rgb(args.reference)
        candidate = load_rgb(args.candidate)
        if reference.shape != candidate.shape:
            msg = "error: reference/candidate size mismatch — export at the same dpi"
            print(msg, file=sys.stderr)
            return 2
        perceptual_report = diff_perceptual(reference, candidate, nodes, args.dpi, threshold=8)
        perceptual_dict = perceptual_report.model_dump(mode="json", exclude_none=True)

    structural_dict = structural_report.model_dump(mode="json", exclude_none=True)
    triage_dict = triage.model_dump(mode="json", exclude_none=True)
    systemic_count = sum(1 for p in triage.patterns if p.classification == "systemic")

    report = {
        "verdict": _verdict(structural_dict, perceptual_dict, systemic_count),
        "structural": structural_dict,
        "triage": triage_dict,
    }
    if perceptual_dict is not None:
        report["perceptual"] = perceptual_dict

    text = json.dumps(report, indent=2 if args.pretty else None)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"verdict: {report['verdict']} → {args.output}", file=sys.stderr)
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
