# Roadmap

Stages are sized so each one ends in something you can open, run or look at —
never a document describing future work. A stage is done when its checklist
passes, not when its code exists.

Specs live in `docs/specs/<stage>/`, each with `spec.md` and a `checklist.md`
fixed at planning time rather than written to match whatever got built.

## S1 — Extract

`PDF → *.ir.json`. The neutral intermediate representation and the extractor
behind it, plus a CLI to produce it.

**Deliverable:** a JSON file describing every element on every page, validated
against a versioned schema, cross-checked for completeness against an
independent converter.

Spec: [`specs/s1-extract/`](specs/s1-extract/spec.md)

## S2 — Tokens and inventory

`*.ir.json (n) → tokens + component candidates`. Palette, type scale, spacing
grid and radii derived from the documents; repeated elements clustered into
candidates with their variant axes.

Takes a **corpus**, not one document: what varies across documents built from the
same template is data, what holds constant is structure. That turns the
unification tolerance from a guess into a measurement.

**Deliverable:** an inventory report — how many distinct atoms, how often each
recurs, which properties vary, and what unification would cost in fidelity.

## S3 — Plugin skeleton and the ceiling

A minimal Figma plugin: import SVG via `createNodeFromSvg`, export PNG, nothing
else. Paired with a comparison command.

**Deliverable:** the measured ceiling — how closely Figma can reproduce a page
even when handed perfect vector. Every later score is judged against this number
instead of against 100%.

## S3.5 — Geometry donor

`PDF region → SVG`, cropped and geometry-only, for the one thing S1's shape
classifier deliberately leaves un-rebuildable: `path`-kind shapes (donuts,
gauges, custom curves), carrying only a bbox and no contour. Sits between S3
(which proved `createNodeFromSvg` works at all) and S4 (whose payload marks
every `path` shape `unsupported` and stops there) because it needed both:
S3's import primitive, and a real payload to show which shapes actually need
it.

**Deliverable:** a CLI command producing a cropped donor SVG per named
region, and a plugin panel that imports it into the existing build frame,
tagged so the already-generic structural-diff export picks it up with no
changes to the payload or verify models.

Spec: [`specs/s3.5-geometry-donor/`](specs/s3.5-geometry-donor/spec.md)

## S4 — Emit and build

`candidates + profile → payload → Figma nodes`. Components, variants, variables,
auto layout, live text. A `manifest.json` mapping candidate to node id, so a
second run updates instead of duplicating.

**Deliverable:** a Figma file containing the rebuilt document as components.

## S5 — Verify and repair

Structural diff (built IR against source IR) and perceptual diff (exported PNG
against reference render), both per region. Then the bounded repair loop, with
vision-assisted hypotheses for perceptual mismatches only.

**Deliverable:** a verification report per region, and a loop that improves the
score until it stops improving — then stops, marking what needs a human.

## S6 — Repair triage

Deterministic structural triage (systemic vs one-off) and perceptual
round-over-round tracking (needs-human after bounded non-improvement), split
off from S5's "repair loop" because vision-driven hypothesis generation and
automatic Figma mutation are each a different kind of problem than the
deterministic pipeline before them.

**Deliverable:** a triage report grouping structural mismatches by pattern,
and a round-tracking tool that marks a perceptual region `needs-human` after
two rounds without improvement — the bookkeeping a human-applied
fix-and-remeasure cycle needs, without automating the fix itself.

## Regression harness

Not a numbered stage — it produces no artifact a later stage reads. Every
real bug found so far lived at a boundary a single-file unit test doesn't
reach (extract↔emit, verify↔repair, TypeScript↔Python), and got caught only
because someone ran the *entire* pipeline by hand against real documents.
This is the set of synthetic fixtures, shaped after those actual bugs, that
catches the same class again without needing a live Figma session.

Spec: [`specs/regression-harness/`](specs/regression-harness/spec.md)

## Out of scope

This project ends at producing a verified design system from documents that
already exist. Generating documents *from* data is the opposite direction and
belongs to whatever system owns the data.

That boundary is not tidiness, it is a constraint:

- **Domain rules cannot live here.** Derived values are business decisions with
  versions and owners. In a domain-neutral tool they would be hardcoded assumptions, which is
  precisely what this project forbids.
- **Third-party data cannot live here.** Source documents, extracts and reference
  tables stay out of a public repository.
- **The data has an owner already.** A generator should read from the system
  that owns the data, not from a copy of it.

What legitimately crosses the boundary is the output of S4: a design system in
Figma, which becomes UI components in whatever renders the documents. Design
flows across; code and data do not.
