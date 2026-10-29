# S2 — Acceptance checklist

Fixed at planning time. A stage is done when every box is checked against a
real run, not when the code exists. Items that turn out to be wrong get struck
through with a reason — never quietly rewritten to match what was built.

Verified against synthetic IR corpora (no real PDF corpus exists yet — source
documents are private and gitignored).

## Runs

- [x] `pdf2figma inventory a.ir.json [b.ir.json ...] -o out.inventory.json`
      succeeds on a multi-document corpus
- [x] Works on a single `*.ir.json` (n=1), producing a weaker but valid report
- [x] `pdf2figma inventory --help` documents every flag and its default
- [x] Missing file and an `IRVersionError` (mismatched `ir_version`) each fail
      with a clear message and a non-zero exit, not a traceback
- [x] `--pretty` indents the JSON; omitted writes compact JSON to stdout when
      no `-o` is given, matching `extract`'s convention

## Report correctness

- [x] Output validates against the model; unknown fields are refused
- [x] `inventory_version` present; a mismatched or missing version raises
      `InventoryVersionError`
- [x] Every tolerance used is echoed back in `tolerances`, so a report is
      self-describing without the command line that produced it
- [x] `CorpusStats` matches the actual input: `documents` equals the number of
      files given, `pages`/`nodes` match their sum across all loaded documents

## Tokens

- [x] Palette: a color used identically across every document in a synthetic
      corpus produces exactly one `ColorToken` with `count` equal to its true
      total occurrences and `roles` correctly split by fill/stroke/text
- [x] Palette: two colors placed just inside `--color-tolerance` of each other
      merge into one token; two placed just outside stay separate — both
      directions asserted, not just the merge case
- [x] Type scale: two different font families at the same size never merge
- [x] Type scale: sizes within `--size-tolerance` of each other merge; `count`
      reflects every text node contributing, `max_delta` reflects the true
      spread
- [x] Spacing: a synthetic page with a known, repeated gap produces a
      `SpacingToken` at that gap value with the right axis and count

## Candidates

- [x] A shape recurring `>= min_occurrences` times becomes a `ShapeCandidate`
      with correct `count`, `documents`, `presence_ratio`
- [x] A shape occurring fewer than `min_occurrences` times is not reported as
      a candidate; it is counted in `unclustered_shapes`
- [x] A shape present in only a subset of the corpus's documents gets
      `variant: true` and the correct `presence_ratio`
- [x] A text style recurring with varying content produces one
      `TextCandidate` whose `sample_texts` contains the distinct strings
      actually observed, capped, with `count` still exact
- [x] Two shapes of the same style but sizes further apart than
      `--size-tolerance` become two separate candidates, not one
- [x] `occurrences` on a high-count candidate is capped (20) while `count`
      stays exact — the cap is visible in the data, not silently misleading

## Privacy

- [x] No absolute path appears in the output — asserted by a test
- [x] No source filename appears in the output — `Occurrence.document` is an
      integer index, structurally incapable of carrying one
- [x] `*.inventory.json` gitignored, verified with `git check-ignore`
- [x] `git ls-files` contains no corpus-derived artifact

## Neutrality

- [x] No hex color literal in `src/pdf2figma/inventory/` outside tests
- [x] No domain vocabulary in `src/pdf2figma/inventory/`
- [x] No hardcoded tolerance value outside the documented CLI defaults —
      every knob that affects clustering is a parameter
- [x] Core `inventory` modules perform no filesystem access; only `cli.py`
      does I/O — asserted by a test, not by convention
- [x] No network call anywhere in the default path

## Engineering

- [x] `ruff check` and `mypy --strict` clean
- [x] New tests pass; synthetic IR corpora are assembled in-test as pydantic
      objects, none committed as JSON fixtures
- [x] No new dependency added — clustering uses only what `pyproject.toml`
      already declares
- [x] `README` documents the `inventory` command against files the reader
      supplies

## Explicitly not in S2

Listed so their absence is not mistaken for an oversight: multi-node composite
("card") detection, radii, a fitted spacing unit, naming of candidates,
anything Figma, calibration of default tolerances against a real corpus (none
exists yet).
