# Regression harness — catching stage-boundary bugs without Figma

Not a numbered pipeline stage — nothing here produces an artifact a later
stage consumes. It's testing infrastructure spanning S1, S3.5, S4 and S5/S6,
written up with a spec and checklist anyway because the reasoning behind
*which* fixtures earn a place here is exactly the kind of decision that
needs to survive the session that made it, same as any stage.

## Why this exists

Three real bugs this project actually shipped were found the same way, by
hand, running the full pipeline against a small corpus of real
third-party reports (kept out of the repo): font-suffix stripping (`_font_of` leaving
`"Helvetica-Bold"` whole, which `loadFontAsync` rejects even though
`Helvetica` is on the system), instance recolor (a reused component
instance keeping its master's fill/stroke instead of its own node's), and
the discovery that `pdftocairo -svg`'s crop flags silently do nothing.
All three lived at a boundary between two stages or two languages — exactly
where a unit test scoped to one file's own logic doesn't reach, and exactly
what a live Figma Desktop click-through catches by accident, once, if
someone remembers to run the whole thing.

That's the gap: everything upstream of a live Figma session is
deterministic (`extract`, `inventory`, `emit`, `convert donor`) and so is
half of what's downstream of it (`verify`, `repair`) — `docs/architecture.md`'s
own stage table says so. None of that needs a human clicking Build. What's
missing isn't new pipeline logic, it's fixtures shaped like the bugs that
already happened, wired into something that runs in one command.

## Goal

Four fixtures, each named after a real bug, plus one command that runs
everything deterministic in this repo:

1. **Instance-reuse-different-color** — a hand-built source IR pair plus a
   hand-built `BuiltDocument` simulating the recolor bug, proving
   `verify.diff_structural` and `repair.triage_structural` still catch it if
   it comes back. Can't test `code.ts` itself (no `figma` global outside a
   live client) — this tests the detector, not the plugin.
2. **Font-suffix, sequential** — `TestFontName` already pins `_font_of` in
   isolation; this adds the two ends of the chain around it: a Python test
   through the *real* `PdfExtractor().extract()` (not just the helper) on a
   synthetic PDF with a `Helvetica-Bold` `BaseFont`, and a TypeScript test
   pinning that `buildPayload` passes a clean `font.family` through
   unmodified — so a future "clever" change to either side can't
   reintroduce the bug at the boundary between them.
3. **Geometry-donor, end-to-end** — S3.5's own tests are real but split:
   `crop_to_donor` gets hand-built SVG strings (no PDF, no poppler),
   `page_to_svg` gets a real poppler call (no crop logic). Nothing runs them
   together through the actual CLI against a synthetic PDF with several
   real path regions. This adds that, still with zero third-party data — a
   synthetic PDF drawing two triangles (classify as `path` per S1's
   heuristic — not a rect, not exactly one line, not four curves) plus a
   text run overlapping one of them, so the text-exclusion behavior is
   exercised against genuine geometric overlap, not just an isolated
   `<use>` fixture.
4. **Schema sync, TS ↔ Python** — the `stroke_color`/`strokeColor` mismatch
   (fixed with a pydantic `alias`) is a class of bug, not a
   one-off: `PayloadNode` is hand-duplicated between `emitter/src/payload.ts`
   and `figma-plugin/src/code.ts` *by design* (their own comments say so —
   two independent TS module systems, "keep the two in sync by hand"), and
   `BuiltNode`/`BuiltFont` cross the Python/TypeScript line entirely with no
   shared type at all. A test that reads all three field-name lists and
   diffs them can't stop someone from adding a field with the wrong casing,
   but it turns that mistake into a failing test instead of a silent
   `None` three stages later.

Then **one command** (`scripts/verify-regression.sh`) running the existing
suites (`pytest`, `ruff`, `mypy --strict`, emitter's `npm test` + `tsc`,
plugin's `tsc`) plus these four — everything in this list is already
individually runnable; the value add is that nobody has to remember the
five separate commands or which directory each one runs from.

## Non-goals

- **Testing `figma-plugin/src/code.ts` itself.** The global `figma` object
  only exists inside a live plugin sandbox — there is no headless
  implementation to import. Every fixture here tests the *consumer* of what
  the plugin produces (`verify`, `repair`) or the *producer* of what it
  consumes (`emit`), never the plugin's own logic. This was true before
  this stage and stays true after it.
- **Replacing the manual Figma Desktop step.** Build, Import donors, Export
  built IR stay a human clicking three panels in order. That's an
  architectural dead end (`docs/architecture.md`: "the build step requires
  Figma Desktop. Headless is impossible"), not a gap this fixes. The goal
  is narrower: that step should only be *necessary* when the plugin's own
  code changes, not on every verify/repair run.
- **A TypeScript AST parser for the schema-sync check.** The three
  interfaces this checks are flat, hand-written, and stable enough that a
  regex over `identifier: type;` / `identifier?: type;` lines is exact for
  what exists today — matching `test_privacy.py`'s own precedent of a
  regex source-scan over a full parser for a small, well-understood
  pattern. It gets confidently wrong on anything nested or generic; it
  isn't asked to handle either.
- **Committing real `built.json`/`*.ir.json` as golden fixtures.**
  `roadmap.md`'s own boundary — "third-party data cannot live here" — rules this
  out regardless of how convenient a real corpus would be as a
  fixture. Every fixture in this stage is built the same way
  `tests/fixtures/synthetic.py`/`synthetic_ir.py` already build theirs: by
  hand, in code, coordinates chosen next to the assertion that checks them.
- **CI wiring.** `scripts/verify-regression.sh` is the thing a CI job would
  call, but there's no CI config in this repo to add it to yet, and
  inventing one wasn't asked for.

## The four fixtures

### 1. Instance-reuse-different-color

Lives in `tests/test_regression_instance_recolor.py`. Two source `ShapeNode`
(or `TextNode`) fixtures with different `fill`, modeling two occurrences of
one component candidate. Two `BuiltDocument`s: one where each built node's
fill matches its own source node (the fixed behavior — both `matched`), one
where the second's built fill wrongly equals the first's (the bug — the
second is `mismatched:fill`). Both go through `diff_structural`, and the
buggy one's report goes on through `triage_structural` to confirm the
pattern groups as expected. This doesn't need `candidateId` or masters at
all — `verify` never sees a master, it compares built nodes to source nodes
by id — which is itself worth stating plainly in the test's docstring,
since it's easy to assume the fixture needs to model the master/instance
relationship when it doesn't.

### 2. Font-suffix, sequential

Two tests, one per language, both new:

- `tests/test_extract.py` (or a new `TestFontNameEndToEnd` class in it):
  `PdfExtractor().extract()` on a PDF whose one font object's `BaseFont` is
  `Helvetica-Bold` (needs `tests/fixtures/synthetic.py::build_pdf` to accept
  the font name as a parameter — currently hardcoded to `Helvetica`; a
  small, backward-compatible addition, default unchanged). Asserts the
  resulting `TextNode.font.family == "Helvetica"` — through the real
  extractor, not `_font_of` called directly.
- `emitter/test/payload.test.ts`: `buildPayload` on an `IRDocument` whose
  text node already carries a clean `family: "Helvetica"` (what real
  `extract` output looks like today). Asserts the payload's
  `font.family` is exactly `"Helvetica"`, unchanged — pinning that
  `payload.ts` is a pure pass-through for this field and never re-derives
  it, which is what makes the Python-side fix actually suffice.

### 3. Geometry-donor, end-to-end

`tests/test_convert_donor_cli.py`. A synthetic single-page PDF (built with
`tests/fixtures/synthetic.py::build_pdf`, raw content-stream operators, no
binary fixture) drawing two small filled triangles at known, far-apart
positions plus a text run positioned to overlap one triangle's bbox. Real
`PdfExtractor().extract()` gets the two `path`-kind node ids and their
bboxes; both the PDF bytes and the extracted IR get written to `tmp_path`
files, then `pdf2figma.cli.main(["convert", "donor", ...])` runs for real —
real `pdftocairo` subprocess, real `crop_to_donor`. Assertions: each
resulting donor SVG contains geometry belonging only to its own triangle
(distinguished by fill color, since the two triangles are given different
fills) and none of the other's; the donor whose bbox overlaps the text run
contains no `<use>` element despite the geometric overlap; each donor's
`viewBox` matches its own requested bbox.

### 4. Schema sync, TS ↔ Python

`tests/test_schema_sync.py`. Reads `emitter/src/payload.ts` and
`figma-plugin/src/code.ts` as plain text (no `tsc`, no AST — see
non-goals), regex-extracts the field names of `interface PayloadNode`
(both files) and `interface BuiltNode` (plugin only). Compares:

- `PayloadNode` fields, `payload.ts` vs `code.ts` — same language, both
  hand-maintained copies of one shape; any difference is drift.
- `BuiltNode` fields, `code.ts` (camelCase, as written) vs Python's
  `verify.model.BuiltNode` (each field's pydantic `alias` if it has one,
  else its own name) — the actual cross-language boundary the real bug
  crossed.
- `PayloadFont`/`BuiltFont` similarly, since they carry the same risk and
  the check is nearly free once the machinery exists for `PayloadNode`/
  `BuiltNode`.

A deliberately narrow regex (`^\s*(\w+)\??:\s*`) over each interface body —
extracted by matching the `interface Name { ... }` block first, so it never
has to reason about anything outside it.

## `scripts/verify-regression.sh`

Bash, matching `probe-pdf.sh`/`run-pipeline.sh`'s existing style
(`set -euo pipefail`, resolved tool paths, a clear section per phase):
Python (`pytest`, `ruff check`, `mypy --strict`), emitter (`npm test`, which
already runs `tsc` first, per its own `package.json`), plugin (`tsc
--noEmit`). Exits non-zero on the first failing phase. Prints which phase
it's running, not just pass/fail at the end, so a failure is traceable
without re-running each command manually to find which one broke.

## Verification

- Every new fixture is exercised by running it and confirming it actually
  fails when the bug it's named after is reintroduced by hand (flip the
  fix, watch the new test go red, revert) — not just that it passes against
  currently-correct code, which would only prove the fixture doesn't
  crash.
- `scripts/verify-regression.sh` run for real, confirmed to exit 0 against
  a clean tree and non-zero against a deliberately broken one (same
  flip-and-revert check, at the script level).
- No new fixture touches `work/`, a real PDF, or a real `built.json` —
  checked by the same discipline `test_privacy.py` already enforces for S1,
  extended by inspection here rather than a new automated scan (the four
  new test files are small enough to read in full).

## Risks

- **The schema-sync regex is exact for today's three interfaces and nothing
  else.** A future interface with a computed/generic field, or a
  `//`-commented-out field left in the source, could confuse a
  line-oriented regex. Scoped deliberately (see non-goals); worth
  revisiting if any of these three interfaces stops being flat.
- **Fixture 1 proves the detector, not the fix.** It cannot catch a
  regression in `code.ts` itself — only confirms that *if* the bug
  reappears in the built output, `verify`/`repair` still notice. The
  plugin's own correctness still rests on the manual Figma Desktop
  walkthrough, same limitation every prior stage's plugin half already
  carries.
- **`verify-regression.sh` doesn't run `figma-plugin`'s `npm run build`,
  only `tsc --noEmit`.** A build-time-only failure (unlikely, but the two
  aren't identical) wouldn't be caught. Cheap to add if it's ever a real
  gap; not added speculatively.
