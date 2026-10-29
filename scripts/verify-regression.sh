#!/usr/bin/env bash
#
# verify-regression.sh — every deterministic-code check this repo can run
# without a live Figma session, in one command.
#
# Three real bugs (font-suffix stripping, instance recolor, the pdftocairo
# vector-crop flags that turn out not to work) were all found by hand,
# running the whole pipeline against real documents. This runs the
# synthetic-fixture regression suite for that same class of bug — see
# docs/specs/regression-harness/spec.md — plus every existing test/lint/
# typecheck command, so nobody has to remember five commands across two
# languages and three directories. Building or clicking anything inside
# Figma Desktop stays manual; nothing here can automate that.
#
# Usage: ./scripts/verify-regression.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

PYTHON=".venv/bin/python"
[ -x "$PYTHON" ] || { echo "error: $PYTHON not found. See README.md's Install section." >&2; exit 1; }

command -v node >/dev/null 2>&1 || { echo "error: node not found." >&2; exit 1; }

echo "-- python: pytest --" >&2
"$PYTHON" -m pytest -q

echo "-- python: ruff --" >&2
".venv/bin/ruff" check src tests

echo "-- python: mypy --strict --" >&2
".venv/bin/mypy"

echo "-- emitter: npm test (runs tsc first) --" >&2
( cd emitter && npm test --silent )

echo "-- figma-plugin: tsc --noEmit --" >&2
( cd figma-plugin && npx tsc --noEmit )

echo
echo "-- all regression checks passed, no Figma session required --"
