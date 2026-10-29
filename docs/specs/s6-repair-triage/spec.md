# S6 — Repair triage

S5's own deliverable bundled two things: a verification report, and "a loop
that improves the score until it stops improving." We built the report.
This stage builds the bookkeeping the loop needs — pattern-grouping for
structural mismatches, round-over-round tracking for perceptual ones —
without automating the parts that genuinely need either an agent's eyes or
write access to a live Figma file.

## Goal

Two tools, neither of which fixes anything:

- `pdf2figma repair structural` groups a structural report's non-`matched`
  regions by what actually diverges, and says whether that pattern is
  `systemic` (worth fixing in the emitter or extractor) or `one-off`.
- `pdf2figma repair perceptual-round` tracks a perceptual report's low
  scores across repeated runs and marks a region `needs-human` once it's
  gone `--needs-human-after` rounds without improving.

A third, `pdf2figma repair crops`, saves the reference/candidate/diff images
for a set of regions — the inputs a hypothesis-writing step needs, prepared
so that step doesn't have to happen inside this CLI.

## Non-goals

- **Agent-classified structural triage.** `architecture.md` frames this as
  an agent's job, but the grouping key is syntactic — which field diverges
  and how — and a human reading the same notes would group them the same
  way. Deterministic, tested, no LLM call, no cost.
- **Automatic Figma mutation.** Nothing here writes to a live Figma file.
  Applying a fix is still a person editing the build by hand, re-exporting,
  and re-running `verify` — the same manual round-trip every other
  Figma-touching step in this project already requires. An auto-apply
  plugin panel is real, separate work with no genuine visual defect on hand
  to prove it against.
- **Generating the hypothesis itself.** `prepare_crops` produces exactly
  what `architecture.md` says a hypothesis-writing agent needs — a
  reference crop, a candidate crop, a diff map, and the region's own IR
  (already in `doc.ir.json`). Writing the actual hypothesis text is a
  separate, explicit step — ask an agent to look at the three images and
  describe what's wrong — not something this tool runs on its own. That
  keeps it consistent with the project's "offline and keyless by default"
  principle: no LLM call is baked into the pipeline.
- **A full run against a real visual defect.** Still no real PDF with a
  genuine perceptual mismatch on hand — same limitation S5 already flagged
  for its own perceptual half. `track_rounds`' bookkeeping is verified
  against manufactured round sequences, not a real repair.

## Structural triage

Takes one or more already-loaded `StructuralReport`s (S5's own model — no
new version/loader needed, `verify_version` already covers it). For every
region that isn't `matched`:

- `mismatched` — a `pattern_key` built from which fields its `notes`
  mention: `"bbox delta"` → `bbox`, `"fill"` → `fill`, `"stroke"` → `stroke`,
  `"text"` → `text`. A region wrong in more than one way keys on all of
  them (`mismatched:bbox+fill`) — it's one region, but it belongs in both
  groups.
- `missing` — keys off S5's `--payload`-derived reason when there is one
  (`missing:path-geometry-unavailable`), else `missing:no-context`.
- `extra` — always its own group.

A pattern seen in `>= --systemic-threshold` regions (default 2, matching
S2's `min_occurrences` default) is `systemic`; below that, `one-off`. Each
known key gets a short, fixed hint (e.g. `fill` → "check candidate matching
against the palette or the plugin's fill-reading") — a pointer to where to
look, not a diagnosis.

Occurrences are `{document, id}` pairs, `document` being the index of which
input report a region came from — mirrors S2's `Occurrence`, and matters
for the same reason: a real extractor's node ids (`p0.t5`) repeat across
different documents, so triaging several reports together needs to know
which one each occurrence belongs to.

## Perceptual round tracking

`track_rounds` compares the current `PerceptualReport` against the previous
round's `PerceptualRoundReport` (or nothing, for a first run). Only regions
currently below `--threshold` are tracked — a region that has climbed back
above it simply stops appearing; its full history still lives in the
underlying perceptual reports, this view is only "what still needs
attention right now."

- First time seen → `new`.
- Score improved since last round → `improved`, and the non-improvement
  counter resets to 0.
- Otherwise → the counter increments; once it reaches
  `--needs-human-after` (default 2, `architecture.md`'s own bound), the
  region becomes `needs-human` and the loop — wherever it runs, by hand or
  otherwise — should stop retrying it.

`--hypotheses hyps.json` (`{"region-id": "free text"}`) sets or overrides a
region's `hypothesis` field for this round. Without a new one, a previous
round's hypothesis carries forward unchanged — the field is a place to keep
what was already figured out, not something this tool ever fills in.

## `prepare_crops`

Reuses S5's `crop_region`/`write_diff_map`
(`src/pdf2figma/verify/perceptual.py`) to save, per requested region id, a
reference crop, a candidate crop and a diff map to an output directory.
That's the exact input set `architecture.md` describes for hypothesis
generation, plus the region's IR node — already sitting in `doc.ir.json`,
nothing new to produce for it.

## Verification

- Structural triage and round tracking are both fully deterministic and
  unit-tested against hand-built report fixtures — no images, no Figma, no
  agent involved anywhere in the tested code path.
- `prepare_crops` is thin — it's S5's already-tested cropping logic, called
  per id. Covered lightly: the right files land with the right names.
- No Figma Desktop step this stage. Nothing here touches the plugin.
