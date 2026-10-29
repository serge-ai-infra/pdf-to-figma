# S1 — Acceptance checklist

Fixed at planning time. A stage is done when every box is checked against a real
run, not when the code exists. Items that turn out to be wrong get struck through
with a reason — never quietly rewritten to match what was built.

Verified against a real multi-page infographic PDF plus synthetic
fixtures. 27 tests, ruff and mypy --strict clean.

## Runs

- [x] `pdf2figma extract <pdf> -o out.ir.json` succeeds on a multi-page document
- [x] `--pages 2-3` extracts only those pages
- [x] `pdf2figma extract --help` documents every flag
- [x] Missing file and unreadable PDF each fail with a clear message and a
      non-zero exit, not a traceback
- [ ] **Encrypted PDF** — not exercised. No encrypted sample to hand; the generic
      handler converts any reader failure into `ExtractError`, but that path is
      unproven for this case specifically.

## IR correctness

- [x] Output validates against the model; unknown fields are refused
- [x] `ir_version` present; loading a document with a different or missing
      version raises `IRVersionError`
- [x] Coordinates are top-left with y down, verified against a synthetic PDF with
      a rect at a known position, within 0.01pt
- [x] Page dimensions match `pdfinfo` (612×792pt on every page)
- [x] Every node has a non-degenerate bbox contained in its page
- [x] Colors are sRGB hex; gray and CMYK operands are normalized
- [x] Text runs carry `color_confidence: exact` — pdfplumber reports the fill per
      character, so color is the document's own value, not inferred from paint
      order. `--no-text-color` yields `unknown`, never a guess.
- [x] Shape classification matches the spec on synthetic fixtures
      — rect and line asserted directly; ellipse and path are covered by the
      documented aspect/point heuristic and exercised on the real document
      (on one real page)

## Completeness

- [x] Cross-check against an independent converter: ~130 shapes in the IR against
      ~110 non-glyph paths from `pdftocairo -svg` on the same page — same order of
      magnitude, difference explained by the two tools grouping primitives
      differently
- [x] Text reproduces `pdftotext`: **zero** tokens lost across four pages
      (the IR has a few more tokens than `pdftotext`). The extra are ZapfDingbats glyphs,
      which encode as `3` and which `pdftotext` drops — extraction is more
      complete than the reference, not less.
- [x] No page yields zero nodes

## Privacy

- [x] No absolute path appears in the output — asserted by a test
- [x] No source filename appears in the output — asserted structurally: the
      field does not exist and the extractor receives bytes
- [x] `work/`, `*.ir.json` and `*.pdf` gitignored, verified with `git check-ignore`
- [x] `git ls-files` contains no PDF, no extract, no third-party-derived artifact

## Neutrality

These make the "no coupling" requirement testable rather than aspirational.

- [x] No hex color literal in `src/` outside tests
- [x] No domain vocabulary in `src/` — checked against identifiers and string
      literals rather than raw source, so prose about how a library "reports" a
      value does not trip a rule meant for `chart_type`
- [x] No hardcoded page size, margin or grid constant
- [x] Core code performs no filesystem access; only `cli.py` does I/O — asserted
      by a test, not by convention
- [x] No network call anywhere in the default path

## Engineering

- [x] `ruff check` and `mypy --strict` clean
- [x] 27 tests pass; synthetic PDFs are assembled in-test, none committed as binary
- [x] Every dependency permissive — pdfplumber MIT, pydantic MIT, pdfminer.six
      MIT, pillow MIT-CMU, numpy BSD. No AGPL in the tree.
- [x] `README` documents install and the extract command against a file the
      reader supplies

## Explicitly not in S1

Listed so their absence is not mistaken for an oversight: clustering, tokens,
component candidates, anything Figma, font extraction and repair, chart or
dataset recovery, rotated text (detected and warned about, not corrected).
