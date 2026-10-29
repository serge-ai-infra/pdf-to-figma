# S5 — Acceptance checklist

Fixed at planning time. A stage is done when every box is checked against a
real run, not when the code exists. Items that turn out to be wrong get struck
through with a reason — never quietly rewritten to match what was built.

Split like S4: the Python half (`pdf2figma.verify`) is verified by an
automated suite; the plugin's new export panel has no headless runner and is
verified by a manual walkthrough in Figma Desktop.

## Structural diff

- [x] A source node whose id, bbox (within tolerance), fill/stroke and text
      all match the built node is reported `matched`
- [x] A bbox delta beyond `--bbox-tolerance` is reported `mismatched` with the
      actual delta, not just a boolean
- [x] A fill/stroke/text difference is reported `mismatched` with both values
      in `notes`, in the "X, expected Y" form
- [x] A source node with no corresponding built id is reported `missing`
- [x] A built id with no corresponding source node is reported `extra`,
      never silently ignored
- [x] `--payload` attaches the emitter's own `unsupportedReason` /
      unmatched-`candidateId` to a `missing` region when one is on record,
      without changing its status
- [x] Report totals (`matched`/`mismatched`/`missing`/`extra` counts) match
      the actual region list, not just a big flat array a reader has to count

## Perceptual diff

- [x] A region cropped identically from both images reports ~100% match
- [x] An injected pixel difference inside one region's crop is caught and
      does not leak into a neighboring region's score
- [x] A degenerate region (zero width or height, e.g. a `line`) is noted, not
      silently dropped from the report
- [x] A region whose bbox falls outside either image's bounds is noted, not
      silently dropped or crashing the run
- [x] `crop_region` uses `dpi/72` on the source's point bbox, matching the
      ratio S3 already validated makes reference and Figma-exported pixels
      comparable without resampling
- [x] `scripts/compare-images.py`'s CLI behavior is unchanged after moving its
      comparison core into `pdf2figma.verify.perceptual` — same flags, same
      output, verified by a manual run since the script has no pytest
      coverage of its own

## Plugin export panel (manual, Figma Desktop)

Verified 2026-08-11: rebuilt S4's demo payload (`work/demo/doc0.payload.json`,
7 nodes — header, 3 standard cards, 1 variant card, 1 one-off ellipse, 1 text
node naming an unloadable font), exported panel 4's `build.built.json`, ran
`verify structural` against the source IR with `--payload` enrichment.

- [x] Every top-level node in the build frame is tagged with `sourceNodeId`
      after a build — the prerequisite this whole stage depends on — confirmed
      by the export itself succeeding: 6 of 7 payload nodes appeared, keyed by
      their exact source ids
- [x] Exporting the build frame produces a `*.built.json` whose node ids are
      exactly the payload's node ids — `d0.header`, `d0.card0-3`, `d0.oneoff`,
      none renamed or dropped except the one genuinely unbuilt node
- [x] A built node's bbox, converted back through `structural diff`, matches
      the source IR's bbox within a small tolerance — every region's
      `bbox_delta` was ~1e-5–1e-6pt, pure px→pt→px float noise
- [x] Running `verify structural` against a real export correctly reports the
      font-load skip and the `path`/`image` nodes from S4's own demo as
      `missing`, and everything else as `matched` — `d0.badfont` reported
      `missing` with the payload-derived context note (no
      `unsupportedReason` recorded for a build-time font failure, exactly as
      documented); all 6 built nodes reported `matched`, 0 `mismatched`,
      0 `extra`

## Engineering

- [x] `ruff check` and `mypy --strict` clean on `src/pdf2figma/verify/`
- [x] New tests pass (24 new: 15 structural + 9 perceptual); synthetic
      IR/PNG fixtures assembled in-test, none committed as binary or JSON
      fixtures
- [x] No new Python dependency — `pdf2figma.verify` uses only what
      `pyproject.toml` already declares (`pillow`, `numpy`, already present
      for the `compare` extra)
- [x] `tsc --noEmit` clean on `figma-plugin/`; `npm run build` produces
      `code.js`
- [x] `*.built.json`, `*.structural.json`, `*.perceptual.json` gitignored,
      verified with `git check-ignore`
- [x] `README.md` / `figma-plugin/README.md` document the new commands and
      panel

## Explicitly not in S5

Listed so their absence is not mistaken for an oversight: the repair loop
(structural auto-fix, vision-assisted perceptual hypotheses, bounded
iteration, needs-human marking), any LLM/agent involvement, region
segmentation beyond one-node-per-region, judging whether a `missing` region
is acceptable, a full end-to-end perceptual run against a real PDF (no real
document available this pass).
