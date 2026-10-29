# S2 — Tokens and inventory

Turn a corpus of IR documents into a report: what recurs, how often, how much
it varies, and what unifying it would cost.

This stage is where the project first looks across documents instead of at
one. A single card is a shape. Thirty cards built from the same template are
evidence of a component — but only a corpus can say which differences between
them are the template and which are the data. See
[`../../architecture.md`](../../architecture.md#several-documents-of-the-same-standard).

## Goal

`pdf2figma inventory a.ir.json [b.ir.json ...] -o out.inventory.json` produces
a validated, versioned report: a color palette, a type scale, a spacing grid,
and a set of recurring atoms (shapes and text styles), each with an occurrence
count, how many documents it appears in, and how much its instances vary.

## Non-goals

Explicitly out of this stage, to keep it finishable and to keep its
limitations from being mistaken for oversights:

- **Multi-node composites.** "Thirty cards collapse into one component" is
  architecture.md's stated ambition, but detecting a card — a recurring group
  of a background shape plus overlaid text and icons — needs a spatial
  grouping step (containment, proximity) with real heuristic risk: it needs a
  container shape to anchor on, and not every repeated layout has one. S2
  clusters individual nodes only. Composite grouping is deferred to whichever
  later stage takes it on.
- **Radii.** IR 0.1 has no corner-radius field on `ShapeNode`, and a rounded
  rect almost certainly classifies as `path` today — the near-square ellipse
  test fails on a rectangle, and the raw curve points needed to detect
  rounded corners are not retained past classification (see
  `extract/pdf.py::_classify_curve`). Computing this would mean extending S1's
  extractor and bumping `IR_VERSION` from inside S2's scope. Left as a
  documented gap.
- **Anything Figma.** Emitting components, variables or nodes is S4. This
  stage's output is a report a person or a later stage reads, not a build.
- **Naming.** A candidate gets an id, not a name like "primary button." Naming
  is the optional, off-by-default LLM step architecture.md describes
  separately.
- **A "spacing unit."** Fitting a single grid unit (e.g. "everything is a
  multiple of 8pt") to the observed gaps is a stronger claim than clustering
  the gaps themselves and is not attempted here. The output is the histogram
  of common gaps, not an inferred base unit.

## Stack

Pure Python, no new dependency. `pydantic` (already a dependency) for the
model. Clustering is simple enough to hand-roll — sort-and-walk for scalars,
greedy nearest-centroid for colors — so this stage deliberately does not pull
in `numpy` or `scikit-learn` for it. See [`cluster.py`](#clustering).

## Input

One or more `*.ir.json` files, loaded with `pdf2figma.ir.load` (same version
check as everywhere else: a mismatched `ir_version` is a refusal, not a silent
upgrade). A single document works; the corpus-vs-content distinction that
makes `variant` and `presence_ratio` meaningful gets stronger with more
documents, same caveat architecture.md already states for componentize.

## The report

```
Inventory      inventory_version, corpus: CorpusStats, tolerances: Tolerances,
               palette: [ColorToken], type_scale: [SizeToken],
               spacing: [SpacingToken], shape_candidates: [ShapeCandidate],
               text_candidates: [TextCandidate],
               unclustered_shapes: int, unclustered_text: int
CorpusStats    documents, pages, nodes
Tolerances     color, size, spacing, min_occurrences
```

**Tokens.**

```
ColorToken     hex, count, max_delta, roles {fill, stroke, text: count}
SizeToken      family, weight?, italic, size, count, max_delta
SpacingToken   axis: x | y, gap, count, max_delta
```

**Candidates.** Atoms only — one node's worth of geometry and style, not a
group of nodes.

```
ShapeCandidate  id, shape, fill?, stroke_color?, stroke_width?, width, height,
                count, documents, presence_ratio, variant, max_size_delta,
                occurrences: [Occurrence]
TextCandidate   id, family, weight?, italic, size, color?, count, documents,
                presence_ratio, variant, sample_texts: [str],
                occurrences: [Occurrence]
Occurrence      document: int, page: int, node_id: str
```

`Occurrence.document` is an index into the input file list, never a path or
filename — the same privacy property the IR already has, and asserted the
same way: by a test, not by review.

`occurrences` is capped (20 entries) with the true `count` reported alongside,
so truncation is visible in the data rather than silently misleading a reader
who assumes the list is exhaustive.

**Every tolerance is a parameter, reported in the output.** Deciding "these
count as the same color / size / gap" is exactly the kind of guess
architecture.md insists on making explicit rather than burying in a heuristic.
The CLI defaults (`--color-tolerance 6`, `--size-tolerance 0.5`,
`--spacing-tolerance 1.0`, `--min-occurrences 2`) are **not validated against a
real corpus** — none exists yet, source PDFs are private and gitignored — and
this is recorded here rather than presented as calibrated.

**Versioned**, same discipline as the IR: `inventory_version` mismatch is an
error, `load()` refuses rather than migrates.

## Clustering

One primitive, used three ways, rather than three bespoke implementations.

**Scalars** (font sizes, spacing gaps): sort ascending, walk once, start a new
cluster when a value is more than `tolerance` from the current cluster's
running mean. Deterministic, `O(n log n)`. Boundary-sensitive by construction:
a value sitting exactly at the tolerance edge between two real groups can land
in either one depending on scan order. This is a known limit of a single-pass
1-D clustering, not hidden — `max_delta` on the resulting token shows how far
a cluster's members actually spread.

**Colors** (3-D, can't just sort): processed in order of descending frequency,
then hex ascending for determinism, and assigned greedily to the nearest
existing cluster centroid — plain Euclidean distance over sRGB `(r, g, b)`,
**not** a perceptual metric like ΔE. That's cheap and dependency-free, and
adequate for deduplicating near-identical swatches (anti-aliasing samples,
export rounding); it is the wrong tool for judging whether two colors that
look similar but are meant to be distinct should merge, and the tolerance
default is deliberately tight (6, out of a ~441 max) to stay on the safe side
of that. If a color falls outside every existing centroid's tolerance it
starts a new cluster; centroids update as a running average of their members.

The palette's color clustering runs **once** and its cluster assignments are
reused by the candidate builder, so a fill and a token disagree about whether
two colors are "the same" never happens by construction.

## Tokens

- **Palette** — every `Color` used as text color, shape fill, or shape stroke,
  across the whole corpus, clustered once (above). `roles` on each token
  breaks down how it's used, because a color that's only ever a stroke reads
  differently than one that's a dominant fill.
- **Type scale** — text nodes grouped by `(family, weight, italic)` exactly —
  two different font families are never the same token regardless of size —
  then sizes within each group clustered.
- **Spacing** — per page, the nearest-neighbor gap in each of the four
  directions (up/down/left/right) for every node, where "neighbor" means the
  closest other node whose bbox overlaps on the perpendicular axis. Sort-based
  per page, not a full pairwise scan. All gaps across the corpus, split by
  axis (`x` for left/right gaps, `y` for up/down), clustered together.

## Candidates

Atoms, grouped across the whole corpus:

- **Shapes** — bucketed first by exact `shape` kind (`rect`/`ellipse`/
  `line`/`path` — already a discrete S1 classification, never merged across
  kinds), then keyed on `(fill cluster, stroke cluster, stroke-width bucket)`
  reusing the palette's color clusters and an internal, unexposed scalar
  clustering of stroke widths. Within a key, `(width, height)` is clustered
  with 2-D Euclidean distance and the shared size tolerance — same style,
  different size, is a different atom.
- **Text** — keyed on `(family, weight, italic, size cluster, color cluster)`,
  reusing the type scale's size clusters and the palette's color clusters.
  Text *content* is expected to vary within a matching style — that's a
  future property/variable slot, not noise — so `TextCandidate` reports a
  capped sample of the distinct strings actually observed rather than
  clustering on content at all.

A group becomes a candidate only once `count >= min_occurrences` (default 2):
a shape or text style seen exactly once is architecture.md's "instance,
deliberately not generalized" — it is counted in `unclustered_shapes` /
`unclustered_text`, never reported as a spurious one-member candidate.

`presence_ratio = distinct documents the candidate appears in / corpus.documents`;
`variant = presence_ratio < 1.0`. This is the atom-level reading of
architecture.md's "present in some documents only → variant" — the multi-node
variant *axes* it also describes (a card that sometimes has a badge) need
composite grouping and are out of scope here.

## Privacy

Same obligation as the IR, carried forward rather than re-derived:

- `Occurrence.document` is a corpus-list index, never a path or filename.
- No absolute path, no source filename, anywhere in the output — asserted by
  a test.
- Core `inventory` modules perform no filesystem access; only the CLI does
  I/O — asserted structurally, same pattern as `extract`/`ir`.

## Verification

No real corpus exists to test against (source PDFs are private and
gitignored). S2 is exercised entirely against **synthetic IR documents built
directly as pydantic objects** — simpler than S1's byte-level PDF fixtures,
since this stage consumes IR, not PDF bytes. A small synthetic corpus models
"the same template, several documents": a repeated card-background rect with
small jitter in size and fill, a header text with fixed style and varying
content, one rect present in only one document (exercises `variant` /
`presence_ratio`), and one genuinely one-off shape (exercises
`unclustered_shapes`, confirms it never becomes a spurious candidate).

## Risks

- **Color distance is Euclidean RGB, not perceptual.** Two colors a human
  would call clearly different but that are numerically close in RGB can
  merge; two that look similar but sit on opposite sides of a channel
  boundary can split. `max_delta` on the resulting token is the only signal a
  reader has that this happened.
- **Scalar clustering is boundary-sensitive**, as noted above — a value near
  the tolerance edge can join either neighboring cluster depending on scan
  order, not "the right" cluster by some independent standard.
- **Default tolerances are guesses**, not calibrated against a real corpus.
  Expect to revisit them once one exists.
- **Composite grouping is absent.** A card built from a rect, an icon shape
  and a text run today produces three separate atom candidates (or fewer, if
  any of them fail `min_occurrences`), not one "card" candidate. The report
  is honest about counts and recurrence at the node level; it does not yet
  answer "how many distinct cards are there."
