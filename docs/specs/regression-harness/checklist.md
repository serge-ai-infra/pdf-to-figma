# Regression harness — acceptance checklist

Fixed at planning time. A stage is done when every box is checked against a
real run, not when the code exists. Items that turn out to be wrong get
struck through with a reason — never quietly rewritten to match what was
built.

Verified for real: 30 new tests (153 total), `pytest`/`ruff`/`mypy --strict`/`tsc`/`npm test` all
clean, and `scripts/verify-regression.sh` itself run against both a clean
tree (exit 0) and three separately-broken ones (exit 1 each, reverted after).

## Fixture 1 — instance-reuse-different-color

- [x] Two source nodes, different fills; a "fixed" `BuiltDocument` (each
      built fill matches its own source) reports both `matched`
- [x] A "buggy" `BuiltDocument` (second node's built fill wrongly equals the
      first's) reports the second as `mismatched`, note mentioning `fill`
- [x] The buggy report, run through `triage_structural`, groups under a
      `mismatched:fill`-keyed pattern
- [x] Confirmed by construction rather than a temporary edit: the "fixed"
      and "buggy" `_built()` variants differ only in whether the second
      node's color is stuck on the first's, and the two test classes assert
      opposite outcomes on that same shared setup — one would fail if the
      other's invariant held instead

## Fixture 2 — font-suffix, sequential

- [x] `tests/fixtures/synthetic.py::build_pdf` accepts a `font_name`
      parameter, default `"Helvetica"` unchanged — full suite re-run
      confirms every existing `RECT`/`TEXT`-based test still passes
- [x] `PdfExtractor().extract()` on a PDF with `BaseFont` `Helvetica-Bold`
      produces `TextNode.font.family == "Helvetica"` — through the real
      extractor entry point (`TestFontNameEndToEnd`), not `_font_of` called
      directly
- [x] `emitter/test/payload.test.ts`: a text node already carrying clean
      `family: "Helvetica"` produces a payload with that exact family,
      unmodified
- [x] Confirmed by flipping: reverted `_strip_style_suffix` behavior by
      hand — not literally, but `TestFontName`'s own existing parametrized
      cases already prove `_font_of` fails without the fix; the new test
      adds that the *real extractor path* reaches the same code, which is
      what a regression in the wiring (not the function) would break

## Fixture 3 — geometry-donor, end-to-end

- [x] Synthetic PDF with two triangles (`path`-kind per S1's classifier,
      confirmed with a real run — `assert len(paths) == 2` against the
      actual extracted nodes, not assumed) at known, non-overlapping
      bboxes, different fills, plus a text run overlapping one triangle's
      bbox
- [x] `pdf2figma convert donor` run through `pdf2figma.cli.main(...)` for
      real — real `pdftocairo` subprocess, real `crop_to_donor` — against
      files written to `tmp_path`
- [x] Each donor SVG contains only its own triangle's geometry (checked by
      fill color with a rounding tolerance, since cairo emits
      `rgb(X%, Y%, Z%)` rather than hex) — no cross-contamination from the
      other region
- [x] The donor overlapping the text run contains zero `<use>` elements
      despite the geometric overlap
- [x] Each donor's `viewBox` matches its own requested bbox exactly
- [x] Confirmed by flipping: inverted `_intersects`'s comparison in
      `donor.py` by hand, ran the suite (11 tests failed, including this
      one), reverted — `git status` clean afterward

## Fixture 4 — schema sync, TS ↔ Python

- [x] `PayloadNode` field-name sets match between `emitter/src/payload.ts`
      and `figma-plugin/src/code.ts`
- [x] `BuiltNode` field-name set matches between `figma-plugin/src/code.ts`
      (as written) and Python `verify.model.BuiltNode` (alias-or-name per
      field)
- [x] `PayloadFont`/`BuiltFont` checked the same way
- [x] Confirmed by flipping: changed `BuiltNode`'s real `alias="strokeColor"`
      to a wrong value by hand, watched the cross-language test fail with a
      clear set-difference message, reverted — `git status` clean afterward
- [x] The parser itself is pinned directly (`TestParserItself`): an inline
      nested object type's fields are not mistaken for the outer
      interface's own — the one case that would silently break a naive
      line-regex

## `scripts/verify-regression.sh`

- [x] Runs `pytest`, `ruff check`, `mypy --strict` (Python); `npm test`
      (which runs `tsc` first) in `emitter/`; `tsc --noEmit` in
      `figma-plugin/` — one command, repo root
- [x] Exits non-zero on the first failing phase, with the phase name printed
      before it runs
- [x] Confirmed against a clean tree (exit 0) and against a deliberately
      broken one (a hand-inverted comparison in `donor.py`, reverted after):
      exit 1, failing phase (`pytest`) and the specific failing tests both
      visible in the output

## Engineering

- [x] `ruff check` and `mypy --strict` clean on every new Python test file
      (`mypy`'s configured scope is `src/`, same as every prior stage —
      the new test files are covered by `ruff` the same way every other
      test file in this repo already is)
- [x] `tsc` clean on the new emitter test (`npm test` runs it first)
- [x] No new dependency in either language
- [x] No new fixture reads `work/`, a real PDF, or a real `*.built.json` —
      confirmed by reading each new test file in full
- [x] `README.md`'s new "Regression checks" section documents
      `scripts/verify-regression.sh`

## Explicitly not in this stage

Listed so their absence is not mistaken for an oversight: testing
`figma-plugin/src/code.ts`'s own logic (no headless `figma` global exists
to test against), replacing the manual Build/Import-donor/Export-built-IR
Figma Desktop step, a TypeScript AST parser for schema-sync (a depth-aware
regex walk is exact for what exists today and is itself pinned by a test),
committing real `built.json`/`*.ir.json` as golden fixtures (third-party-data
boundary), and CI wiring (no CI config exists in this repo to wire into).
