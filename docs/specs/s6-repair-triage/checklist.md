# S6 — Acceptance checklist

Fixed at planning time. A stage is done when every box is checked against a
real run, not when the code exists. Items that turn out to be wrong get struck
through with a reason — never quietly rewritten to match what was built.

Fully automatable this time — no Figma Desktop step, unlike S3–S5.

## Structural triage

- [x] A mismatch pattern recurring in `>= --systemic-threshold` regions is
      `systemic`; one below that stays `one-off`
- [x] A region wrong in more than one way (e.g. bbox and fill) contributes
      to both pattern groups, not just one
- [x] A `missing` region enriched by S5's `--payload` note keys off that
      reason; a bare one keys off `no-context` instead
- [x] Triaging multiple `StructuralReport` inputs together correctly
      indexes occurrences by which input they came from, so same-named
      node ids from different documents never collide
- [x] Every known pattern key carries a fixed hint string; nothing crashes
      or drops the region silently on an unrecognized one

Manual smoke test against a real S5 export (`work/demo/doc0.ir.json` +
`build.built.json` from S5's Figma Desktop walkthrough) found a real bug:
a `missing` region whose payload context happened to contain the substring
`"kind=text"` picked up the `text`-mismatch hint instead of the generic
`missing` one — naive substring matching leaking across categories. Fixed
in `structural.py::_hint_for` (only applies field hints to `mismatched:`
keys now) and locked down with a regression test
(`test_missing_reason_mentioning_a_field_name_gets_the_missing_hint`).

## Perceptual round tracking

- [x] A region seen for the first time is `new`, not `needs-human`
- [x] A region whose score improves resets its non-improvement counter to 0
- [x] Two consecutive non-improving rounds produce `needs-human`, matching
      `architecture.md`'s own bound (`--needs-human-after 2` by default) —
      confirmed via both the automated suite and a manufactured 3-round CLI
      sequence (82% → 82% → 81%)
- [x] A region that climbs back above `--threshold` stops appearing in the
      round report — checked explicitly, not assumed
- [x] `--hypotheses` overrides a region's hypothesis for the current round;
      omitting it carries the previous round's hypothesis forward unchanged

## `prepare_crops`

- [x] Requesting a set of region ids produces exactly one reference crop,
      one candidate crop and one diff map per id, named by that id
- [x] Reuses `verify.perceptual`'s `crop_region`/`write_diff_map` rather
      than re-implementing cropping

## Engineering

- [x] `ruff check` and `mypy --strict` clean on `src/pdf2figma/repair/`
- [x] New tests pass (21 new: 12 structural + 9 perceptual); fixtures built
      from S5's own models in-test, no committed report or image fixtures
- [x] No new dependency — `pdf2figma.repair` uses only what
      `pyproject.toml` already declares
- [x] `README.md` documents all three subcommands

## Explicitly not in S6

Listed so their absence is not mistaken for an oversight: agent-classified
structural triage, automatic Figma mutation, automated hypothesis
generation (this stage prepares the inputs for one; writing it is a
separate, explicit step), a full run against a real visual defect (no real
PDF with one available).
