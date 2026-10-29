#!/usr/bin/env bash
#
# smoke-demo.sh — run the committed demo PDF through every scriptable stage
# and check the outputs against what the demo is known to contain.
#
# extract -> inventory -> auto-profile -> emit -> convert donor, via
# run-pipeline.sh, into a throwaway directory. Figma is not involved; this
# catches a stage that crashes, silently drops nodes, or stops converting
# units, on a real (if small) document rather than a hand-built fixture.
#
# The expected counts are the demo's, measured when it was added. If a
# deliberate change moves them (a better classifier, say), update them here
# in the same commit and say why.
#
# Usage: ./scripts/smoke-demo.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

PYTHON=".venv/bin/python"
[ -x "$PYTHON" ] || { echo "error: $PYTHON not found. See README.md's Install section." >&2; exit 1; }

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

"$SCRIPT_DIR/run-pipeline.sh" docs/demo/demo.pdf "$OUT" 2>/dev/null

"$PYTHON" - "$OUT" <<'EOF'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
load = lambda name: json.loads((out / name).read_text())

ir = load("doc.ir.json")
inventory = load("doc.inventory.json")
payload = load("doc.payload.json")
donors = load("doc.donors.json")

nodes = ir["pages"][0]["nodes"]
by_kind = {}
for node in nodes:
    kind = node["shape"] if node["kind"] == "shape" else node["kind"]
    by_kind[kind] = by_kind.get(kind, 0) + 1

built = [n for n in payload["nodes"] if n["kind"] != "unsupported"]
unsupported = [n for n in payload["nodes"] if n["kind"] == "unsupported"]
texts = [n for n in built if n["kind"] == "text"]
ir_text = {n["id"]: n for n in nodes if n["kind"] == "text"}

checks = [
    ("IR nodes", len(nodes), 102),
    ("IR text nodes", by_kind.get("text", 0), 61),
    ("IR path shapes (curves only a donor can rebuild)", by_kind.get("path", 0), 35),
    ("IR ellipses (rounded cards must not classify as these)", by_kind.get("ellipse", 0), 0),
    ("recurring shape candidates", len(inventory["shape_candidates"]), 3),
    ("recurring text candidates", len(inventory["text_candidates"]), 8),
    ("payload nodes the plugin can build", len(built), 67),
    ("payload nodes left to donors", len(unsupported), 35),
    ("geometry donors", len(donors["nodes"]), 35),
    ("donors with an empty SVG", sum(1 for d in donors["nodes"] if "<path" not in d["svg"]), 0),
    # The payload paints in px: font size is the IR's pt size x 4/3, like the bbox.
    ("text nodes whose font size isn't pt x 4/3", sum(
        1 for n in texts
        if abs(n["font"]["size"] - ir_text[n["id"]]["font"]["size"] * 4 / 3) > 1e-6
    ), 0),
]

failed = [(label, got, want) for label, got, want in checks if got != want]
for label, got, want in checks:
    print(f"{'ok  ' if got == want else 'FAIL'} {label}: {got}" + ("" if got == want else f" (expected {want})"))

if failed:
    sys.exit(f"\n{len(failed)} demo smoke check(s) failed")
print("\n-- demo smoke run matches --")
EOF
