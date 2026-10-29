# S5 — Verify

Compare a built Figma file back against its source, two ways, per region: does
the geometry and style match exactly (structural), and does it look right
(perceptual)? Produces a report. Does not fix anything.

## Goal

Two new commands read a document's own IR (S1) alongside evidence of what was
actually built, and report where they diverge:

- `pdf2figma verify structural doc.ir.json built.json` — exact, per-node.
- `pdf2figma verify perceptual reference.png candidate.png doc.ir.json` —
  per-pixel, cropped to each node's own region.

`built.json` comes from a new plugin panel that exports the build frame back
into IR-shaped data — the counterpart to S4's payload, in the other direction.

## Non-goals

Explicitly out of this stage:

- **The repair loop.** Roadmap bundles "verification report" and "a loop that
  improves the score" into one deliverable; this pass is the report half
  only. The loop is agent-assisted, vision-driven, bounded-iteration work —
  different enough in kind from a deterministic diff tool that it belongs in
  its own pass, same way S2 split off composites and S4 split off variables.
- **Region segmentation beyond one-node-per-region.** `architecture.md` left
  this an open question ("derived from clustering, or declared in the
  profile"). Using the source IR's own node ids sidesteps the question rather
  than answering it — no new schema, nothing for a user to author before a
  first report exists. A composite region (a whole "card" as one unit) needs
  the composite grouping S2 never built either.
- **Deciding whether a `missing` region is a bug.** A node absent from the
  built output might be `path`/`image` (no geometry ever existed to build) or
  an unloadable font (S4's own documented skip) — or a genuine failure to
  match a candidate that should have matched. The structural diff reports
  `missing` uniformly and, when given `--payload`, attaches the emitter's own
  recorded reason if there is one; it does not judge which misses are
  acceptable. That judgment is exactly what the (deferred) repair loop's
  agent classification step is for.
- **Whole-page perceptual score as the primary signal.** Still computed, for
  continuity with S3's ceiling measurement, but per-region results are what
  this stage exists to produce — a page-level percentage is exactly the
  number architecture.md warns hides a broken region inside a 97%.

## Prerequisite: closing the loop S4 left open

Structural diff needs "built IR," and nothing produces that yet. Two small
gaps in S4 get closed here rather than treated as a separate stage:

1. **Built nodes weren't traceable to their source.** `figma-plugin/src/code.ts`
   tags component *masters* with `candidateId` (for idempotency) but never
   tagged an instance or plain node with *which payload node* it came from.
   Fixed by one more `setPluginData('sourceNodeId', payloadNode.id)` call per
   creation path.
2. **Nothing exports the built tree.** New panel, described below.

## The plugin's export panel

Reads the build frame's direct children — each now carrying `sourceNodeId` —
and reconstructs, per child: `id` (from the tag), `bbox` converted px→pt
(÷4/3, the exact inverse of `payload.ts`'s conversion), fill/stroke from
`.fills`/`.strokes`, and for a text node (found directly, or as an instance's
nested `TEXT` child) its font and characters. Downloads `*.built.json` through
the same Blob-download path S3 already uses for PNG export — the plugin
sandbox still has no filesystem, so nothing about that mechanism changes.

`BuiltNode`/`BuiltDocument` are declared locally in `code.ts`, duplicated from
the Python model rather than imported — the same call made for `Payload` in
S4: small, stable, one-way, and the two projects don't share a module system.

## Structural diff

For every node in the source IR page, look up the same `id` in
`BuiltDocument.nodes`:

- **missing** — in source, absent from built. Includes legitimate S4 skips
  (`path`, `image`, an unloadable font) and real bugs alike; this tool cannot
  tell them apart from IR and built-IR alone.
- **matched** — found, bbox within `--bbox-tolerance` points, fill/stroke/text
  exactly equal.
- **mismatched** — found but off: a bbox delta beyond tolerance, or a
  fill/stroke/text that differs, recorded in `notes` in the
  architecture.md-style form ("fill #336699, expected #3366cc").
- **extra** — a built id with no matching source node. Shouldn't happen from
  this pipeline's own output, but a stale or hand-edited `built.json` can
  produce one, and silently ignoring it would hide exactly the kind of
  surprise this tool exists to surface.

`--payload payload.json` is optional and only annotates `missing` regions
that the emitter already explained (`unsupportedReason`, or a `candidateId`
that never got matched) — it does not change any status, only the note
attached to it.

## Perceptual diff

Reuses `scripts/compare-images.py`'s comparison core — `load_rgb`, `compare`,
`write_diff_map` — moved into `pdf2figma.verify.perceptual` so it's a tested
library function rather than script-only logic; the script itself becomes a
thin CLI wrapper with unchanged behavior (still the whole-page ceiling tool
`figma-plugin/README.md` documents).

`crop_region` converts a source node's bbox (points) to pixel coordinates by
`× dpi/72` — not `dpi/96` — because that is the ratio that made a
`pdftoppm`-rendered reference and a Figma PNG export comparable without
resampling in S3's own measurement (`figma-plugin/README.md`, "Why DPI has to
match, and why the scale is dpi/96" — the plugin exports at `dpi/96` *of CSS
pixels*, which are already 4/3 of a point, so the net PDF-point-to-final-pixel
ratio is `dpi/72` either way). `diff_perceptual` crops both images to every
region and runs `compare()` on each crop; a degenerate region (a `line`'s
zero-height bbox) or one that falls outside either image's bounds is recorded
with a note, never silently dropped from the report.

## Privacy

Same rule as every prior stage's artifacts: no absolute path, no source
filename, anywhere in `built.json`, `*.structural.json` or
`*.perceptual.json`. All three gitignored.

## Verification

- Structural diff is fully unit-testable: synthetic IR (existing
  `tests/fixtures/synthetic_ir.py` builders) against hand-built
  `BuiltDocument` fixtures covering every status.
- Perceptual diff's cropping and comparison logic is unit-testable against
  synthetic PNGs assembled with Pillow — no real PDF or Figma export needed
  to verify the *logic*.
- A full end-to-end perceptual run — real reference PNG, real Figma export —
  needs an actual PDF. Not exercised this pass for lack of one; the report
  format and the per-region logic are verified, the number Figma actually
  produces for a real document is not.
- The plugin's export panel has no headless runner, same as S4's build panel
  — verified by hand in Figma Desktop.

## Risks

- **`missing` conflates bugs with intentional gaps.** Flagged repeatedly above
  because it's the single biggest thing a reader of this report could
  misread — a long `missing` list is not automatically a regression.
- **Per-node regions can be very fine-grained** on a dense page (S1's own
  checklist measured 300–400+ nodes per page). The report scales with node
  count, not with anything a human would call a "region" — a summary by
  status, not just a flat list, matters for this to stay readable.
- **Perceptual crop coordinates assume the reference and candidate PNGs were
  rendered at the same `dpi`** the caller passes in, same requirement S3
  already established and the comparator already enforces (refuses mismatched
  image sizes rather than resampling).
