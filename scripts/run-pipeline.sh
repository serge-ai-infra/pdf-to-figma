#!/usr/bin/env bash
#
# run-pipeline.sh — everything this project can automate, in one command.
#
# extract -> inventory -> auto-profile -> emit, for one PDF. Stops there on
# purpose: building in Figma needs a human clicking in Figma Desktop, which
# nothing can script from outside it. This gets you to the one unavoidable
# click as fast as possible and tells you exactly what to do there.
#
# Usage: ./scripts/run-pipeline.sh <input.pdf> [outdir]
#
set -euo pipefail

usage() {
    sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

[ $# -ge 1 ] || usage 1
case "$1" in -h | --help) usage 0 ;; esac

INPUT="$1"
OUTDIR="${2:-work/pipeline}"

[ -f "$INPUT" ] || { echo "error: no such file: $INPUT" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

# pdf2figma: prefer PATH, fall back to the venv the README's Install section sets up.
if command -v pdf2figma >/dev/null 2>&1; then
    PDF2FIGMA="pdf2figma"
elif [ -x "$ROOT/.venv/bin/pdf2figma" ]; then
    PDF2FIGMA="$ROOT/.venv/bin/pdf2figma"
else
    echo "error: pdf2figma not found. See README.md's Install section." >&2
    exit 1
fi

command -v python3 >/dev/null 2>&1 || { echo "error: python3 not found." >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "error: node not found (needed for emit)." >&2; exit 1; }

EMITTER_CLI="$ROOT/emitter/dist/src/cli.js"
if [ ! -f "$EMITTER_CLI" ]; then
    echo "-- building emitter (first run only) --" >&2
    ( cd "$ROOT/emitter" && npm install --silent && npm run build --silent )
fi

mkdir -p "$OUTDIR"
IR="$OUTDIR/doc.ir.json"
INVENTORY="$OUTDIR/doc.inventory.json"
PROFILE="$OUTDIR/doc.profile.json"
PAYLOAD="$OUTDIR/doc.payload.json"
DONORS="$OUTDIR/doc.donors.json"

echo "-- extract --" >&2
"$PDF2FIGMA" extract "$INPUT" -o "$IR" --pretty

echo "-- inventory --" >&2
# A single document is a weaker corpus than several of the same template
# (see docs/specs/s2-tokens-inventory/spec.md) — still finds whatever
# repeats within this one document.
"$PDF2FIGMA" inventory "$IR" -o "$INVENTORY" --pretty

echo "-- auto-profile (componentizes every recurring candidate found) --" >&2
python3 "$SCRIPT_DIR/auto-profile.py" "$INVENTORY" -o "$PROFILE"

echo "-- emit --" >&2
node "$EMITTER_CLI" "$IR" "$INVENTORY" --profile "$PROFILE" -o "$PAYLOAD" --pretty

echo "-- convert donor (geometry for path-kind shapes emit can't build) --" >&2
# Every rounded bar, donut and curved section header a PDF draws is a
# `path` to S1's classifier, not a `rect` — emit marks all of them
# unsupported (see docs/specs/s3.5-geometry-donor/spec.md). No `--ids`:
# every path-kind node on the page, which on a real report is routinely
# over a hundred — curating that list by hand doesn't scale.
if "$PDF2FIGMA" convert donor "$INPUT" "$IR" -o "$DONORS" --pretty; then
    DONOR_STEP=$'  3b. Panel "5 - Import geometry donors" -> pick '"$DONORS"$' -> Import\n      (after Build, before Export built IR, so it shows up in the diff)'
else
    echo "   (no path-kind shapes on page 1 — nothing to donor-convert)" >&2
    DONOR_STEP="  (no geometry donors needed for this document)"
fi

cat >&2 <<EOF

-- done: everything scriptable is done --

Payload ready at: $PAYLOAD

Now the one step nothing can automate:
  1. Figma Desktop -> Plugins -> Development -> Import plugin from manifest...
     -> pick $ROOT/figma-plugin/manifest.json (once, if not already loaded)
  2. Run the plugin -> panel "3 - Build from payload" -> pick $PAYLOAD -> Build
$DONOR_STEP

That's it if you just want the file. If you also want a validation report:
  4. Panel "4 - Export built IR" -> Export -> save as built.json
  5. ./scripts/validate-build.py $IR <path to built.json> --payload $PAYLOAD
EOF
