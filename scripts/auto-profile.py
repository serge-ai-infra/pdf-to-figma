#!/usr/bin/env python3
"""Generate a profile that componentizes every candidate an inventory found.

Profiles are meant to be data the user authors deliberately — see
architecture.md's anti-coupling rule 3, "shipped profiles are examples only."
This is the one deliberate exception: a *convenience generator* for someone
who wants a reasonable default rather than none, not a default this project
ships silently. Every candidate in the inventory already passed
`--min-occurrences` (it recurs), so componentizing all of them is a
defensible blanket choice — not something this tool decides quietly, since
you have to run it and choose to use its output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_profile(inventory: dict[str, object]) -> dict[str, object]:
    candidates: dict[str, dict[str, object]] = {}

    for shape in inventory.get("shape_candidates", []):  # type: ignore[union-attr]
        candidates[shape["id"]] = {"component": True}

    for text in inventory.get("text_candidates", []):  # type: ignore[union-attr]
        candidates[text["id"]] = {"component": True, "liveText": True}

    return {"candidates": candidates, "defaults": {"component": False, "liveText": False}}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("inventory", type=Path, help="*.inventory.json from `pdf2figma inventory`")
    ap.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    args = ap.parse_args()

    if not args.inventory.is_file():
        print(f"error: no such file: {args.inventory}", file=sys.stderr)
        return 1

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    profile = build_profile(inventory)
    text = json.dumps(profile, indent=2)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        count = len(profile["candidates"])  # type: ignore[arg-type]
        print(f"{count} candidate(s) set to componentize → {args.output}", file=sys.stderr)
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
