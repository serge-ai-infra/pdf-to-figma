#!/usr/bin/env python3
"""Compare two renders of the same page and quantify the difference.

Used two ways, and the distinction matters:

  ceiling   reference render vs. a straight vector import — how closely the
            target editor can reproduce the page when handed perfect input.
            Nothing built by hand can score better than this.

  fidelity  reference render vs. a rebuilt page — the number that actually
            tracks progress. It is judged against the ceiling, never against
            a perfect score, because a perfect score is not reachable.

Reports several metrics on purpose: a single number hides whether a page is
slightly wrong everywhere (antialiasing, harmless) or badly wrong in one place
(a broken component, not harmless).

Whole-page only — for the per-region version this same comparison core feeds,
see `pdf2figma verify perceptual` (S5, `src/pdf2figma/verify/perceptual.py`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdf2figma.verify.perceptual import compare, load_rgb, write_diff_map


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("reference", type=Path, help="ground-truth render")
    ap.add_argument("candidate", type=Path, help="render to evaluate")
    ap.add_argument("-o", "--diff", type=Path, help="write an amplified difference map here")
    ap.add_argument("--threshold", type=int, default=8,
                    help="per-channel delta counted as a real difference (default 8/255)")
    ap.add_argument("--gain", type=float, default=4.0, help="difference map amplification")
    args = ap.parse_args()

    for path in (args.reference, args.candidate):
        if not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 1

    ref = load_rgb(args.reference)
    cand = load_rgb(args.candidate)

    if ref.shape != cand.shape:
        print(
            f"error: size mismatch — reference {ref.shape[1]}x{ref.shape[0]}, "
            f"candidate {cand.shape[1]}x{cand.shape[0]}\n"
            "Export at dpi/72 scale so both come out at the same pixel size. "
            "Rescaling here would blur the differences being measured.",
            file=sys.stderr,
        )
        return 2

    m = compare(ref, cand, args.threshold)

    print(f"size              {ref.shape[1]}x{ref.shape[0]} px")
    print(f"matching pixels   {m['match_pct']:.3f}%  (threshold {args.threshold}/255)")
    print(f"differing pixels  {m['differing_px']:,} ({m['differing_pct']:.3f}%)")
    print(f"mean abs error    {m['mae']:.3f}")
    print(f"rmse              {m['rmse']:.3f}")
    print(f"max delta         {m['max_delta']:.0f}")
    print(f"spread            {m['rows_touched_pct']:.1f}% of rows, "
          f"{m['cols_touched_pct']:.1f}% of columns touched")

    if m["differing_pct"] > 0 and m["rows_touched_pct"] > 80:
        print("\nDifferences are spread across the page — typically antialiasing "
              "or a global offset, not a broken element.")
    elif m["differing_pct"] > 0:
        print("\nDifferences are localized — look at the diff map before trusting "
              "the overall percentage.")

    if args.diff:
        write_diff_map(ref, cand, args.diff, args.gain)
        print(f"\ndiff map          {args.diff}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
