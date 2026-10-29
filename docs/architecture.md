# Architecture

**Status: draft.** Open questions at the bottom are being answered by probes
against real documents. Decisions marked *(unverified)* have not been tested yet.

## Goal

Reproduce a PDF in Figma as a component-based file, with the difference between
source and result measured per region rather than asserted.

Two goals are in tension and the design keeps that tension visible:

- **Fidelity** wants a flat pile of nodes matching the source exactly.
- **Componentization** wants unification — thirty cards collapsing into one
  component with variants.

Unification is lossy: cards in a PDF differ by fractions of a point. So the
tolerance that decides "these are the same component" is an explicit parameter,
and every run reports what unification cost in fidelity. Hiding that tolerance
inside heuristics would make the trade-off unmanageable.

With a single document that tolerance is a guess. With several documents of the
same standard it is measurable — see below.

## Pipeline

```
                         ┌─────────────── ground truth ───────────────┐
                         │                                            │
  PDF ──► extract ──► IR ├──► normalize ──► componentize ──► emit ──► plugin builds
   │                     │        │                                     │
   ├──► render (PNG)  ───┘        └── tolerance, tokens                  │
   ├──► convert (SVG regions) ─────────── geometry donor ────────────────┤
   └──► fonts (extract, install)                                         │
                                                                        ▼
                                        structural diff ◄── export IR + PNG
                                        perceptual diff
                                              │
                                              ▼
                                       verification report
                                              │
                                     repair loop (bounded)
```

### Stages

| Stage | In | Out | Deterministic | Status |
|---|---|---|---|---|
| `extract` | PDF | `*.ir.json` | yes | built |
| `render` | PDF | reference PNG per page | yes | via `pdftoppm` (`scripts/probe-pdf.sh`) |
| `convert` | PDF region | SVG | yes | built (`convert donor`) |
| `fonts` | PDF | font files + install report | yes | not built |
| `normalize` | IR + tolerance | canonical IR + tokens | yes | built, as part of `inventory` |
| `componentize` | canonical IR | component candidates + variants | yes | candidates built (`inventory`); variants not built |
| `emit` | candidates + profile | plugin payload | yes | built (`emitter/`) |
| *plugin build* | payload | Figma nodes + `manifest.json` | yes | built: components, instances, live text; no auto layout or variables |
| `verify` | built IR + PNG vs reference | verification report | yes | built |
| `repair` | report | payload patches | agent-assisted | triage built; patching is manual |

Every stage exchanges files. Any stage can run standalone against a checked-in
fixture, with no PDF and no Figma account.

## Intermediate representation

The IR is the contract, and it is deliberately dumb — geometry, style and text,
no semantics. It carries no chart types, no component names, no domain concepts.

- Origin is **top-left, y-down**, matching Figma. PDF's bottom-up coordinates are
  converted once, at extraction.
- Units are PDF points (1/72"). No pixels, no DPI, until render time.
- **Figma is not in points.** It imports SVG as CSS pixels, where one point is
  4/3px, so a 612×792pt page becomes an 816×1056 frame. The IR stays in points;
  the conversion happens once, in the emitter. Anything built alongside an
  imported reference must use the reference's unit or the two will never overlay,
  and raster export scales by dpi/96 rather than dpi/72.
- Nodes are `text`, `shape` (`rect` | `ellipse` | `line` | `path`) or `image`.
- Colors are normalized to sRGB hex plus alpha. A source color space that is not
  sRGB is recorded, because the conversion caps achievable color accuracy.
- Anything uncertain carries a confidence field rather than a guessed value.
- The IR is versioned; a schema mismatch is an error, never a silent migration.

The same IR describes what was *built* in Figma, exported back by the plugin.
That symmetry is what makes structural diffing possible.

## Verification: two levels

Pixel comparison alone is a poor debugging tool — the metric drops and you don't
learn why.

**Structural.** The plugin exports the built tree back into IR. Comparing source
IR to built IR addresses failures precisely: *node `p1.card.kpi-3` has fill
`#336699`, expected `#3366CC`; bbox off by 1.2pt*. Cheap, exact, unambiguous.

**Perceptual.** Reference PNG rendered from the PDF versus PNG exported from
Figma. Catches what looks structurally fine and wrong to the eye: Bézier
approximations, stroke weights, kerning, antialiasing.

Both compare **per region**, never whole pages. A broken table dissolves into a
97% page-level score and goes unnoticed.

### The ceiling

Figma's renderer cannot match a PDF renderer exactly, so 100% is not the target.
The ceiling is measured, not guessed: import the PDF as SVG, export it straight
back as PNG, compare to the reference render. That number is the maximum any
build can reach. Our score is judged against the ceiling, not against 100%.

## What import is for

Figma has no PDF import. Vector arrives via the macOS clipboard, an SVG file, or
`figma.createNodeFromSvg` in a plugin — the last being the only automatable one.
All three produce flat, unnamed nodes, and Figma ignores `@font-face` in SVG, so
SVG text renders in a substituted font.

So import serves two narrow purposes:

- **Pixel reference.** A high-DPI PNG placed under the build with `difference`
  blend makes discrepancies visible by toggling a layer — no tooling required.
  Raster, not vector: cheaper and it does not bloat the file.
- **Geometry donor.** Selected regions converted to SVG, imported, and wrapped in
  components. Donuts, gauges and custom curves are *inherited rather than
  generated* — the tool never emits Bézier paths of its own. This removes the
  riskiest part of the work and gives exact geometry where it is hardest.
  Cropping happens by filtering the full page's converted SVG down to the
  elements that intersect the target region, not by a poppler crop flag —
  measured directly (S3.5), `pdftocairo -svg -x/-y/-W/-H` silently leaves
  vector output at full page size; the crop flags only affect raster
  formats. See `specs/s3.5-geometry-donor/spec.md`.

Text-to-outline conversion makes each glyph a path, so a text-heavy page becomes
thousands of nodes. Vector import is therefore per-region only, never per-page.

## Fonts

Figma renders only fonts available to the editor, and **no API or plugin can load
a font into Figma**. What that costs depends entirely on the document, so `probe`
answers it before anything else:

- **Standard-14 fonts, not embedded** (Helvetica, Times, Courier, Symbol,
  ZapfDingbats). The good case: these are present on macOS already, metrics are
  standardized, and nothing needs extracting. Documents from reporting libraries
  are frequently in this category.
- **Embedded subsets.** Extract them, repair the subsets into installable files
  (`fontTools`), install them in the OS, work in Figma Desktop.
- **Neither.** A font that is referenced, not embedded, and not installed cannot
  be recovered from the document at all. The metric ceiling drops and the report
  must say so rather than silently substituting.

One caveat that survives every case: the reference render comes from a PDF
renderer with its own font substitution rules, so reference and Figma may disagree
on glyph rasterization even when both name the same family. That gap belongs to
the measured ceiling, not to our bugs.

Consequences, accepted rather than worked around:

- The build step requires Figma Desktop. Headless is impossible — the plugin
  needs an open file. Everything up to that point automates.
- A subset that cannot be repaired caps the achievable metric. The report says
  so explicitly instead of silently substituting a font.
- Writing Variables over REST requires a Figma Enterprise plan; the plugin path
  has no such limit, which is another reason the plugin is mandatory. Reading and
  exporting images over REST works on any plan, so verification automates.

## Where agents belong

The repair loop is agent-assisted, with a strict division:

- **Structural mismatches are fixed by code, not by an agent.** A wrong fill or
  bbox is a bug in the emitter or extractor. An agent only classifies: systemic
  versus one-off.
- **Perceptual mismatches are a vision task.** The agent receives the reference
  crop, the built crop, the difference map and the region's IR, and proposes a
  hypothesis — *donut segments start at 3 o'clock instead of 12*. That is exactly
  what a human does by eye and what cannot be encoded up front.
- **Bounded iteration.** Two consecutive iterations without metric improvement
  mark the region `needs-human` and the loop moves on. Without this an agent
  polishes antialiasing forever.
- **Regions are independent**, which makes them the unit of parallel work.
- **Naming and grouping** (atom/molecule, component names) is the other optional
  LLM step. Off by default; requires a key the user supplies.

## Stack

Polyglot, split exactly along the IR contract.

**Python** — extraction, rendering, image comparison, font repair.

Library choice is constrained by the license, not only by capability. This
project is MIT, so an AGPL dependency would push that obligation onto everyone
who builds on it:

- `pdfplumber` (MIT) for extraction — characters with font, size and fill color,
  plus rects, lines and curves. Enough for the IR, with no copyleft.
- `pypdfium2` (Apache-2.0 / BSD) for rendering reference images.
- `scikit-image` (BSD) for comparison, `fontTools` (MIT) for font repair.
- PyMuPDF is the more capable extractor and is deliberately **not** used: it is
  AGPL-3.0 unless separately licensed.
- Poppler CLI tools (GPL) are invoked as external binaries — by `probe`
  (a shell script) and by `convert/poppler.py` (S3.5, over stdin/stdout
  pipes, no temp files). Execution is not linking, and no library code
  depends on them; which caller does the executing doesn't change that.

**TypeScript** — the Figma plugin, where there is no alternative, and the
emitter that feeds it.

Python writes JSON, TypeScript reads it. Neither knows about the other.

## Several documents of the same standard

A corpus beats a generator for the one question componentization actually turns
on: which differences are structural and which are data.

Within a single document, deciding whether two cards are the same component means
picking a tolerance and hoping. Across documents built from the same template, the
answer is observable — what varies between them is content, what holds constant is
the component. The tolerance stops being a knob to guess at and becomes a
calibrated number, and its residual error is reported rather than assumed.

A corpus also supplies variants directly. Different documents include different
module sets, different states, different densities; those are exactly the variant
axes a component needs, discovered instead of invented.

So `componentize` takes *n* IRs, not one:

- elements stable across the corpus in geometry and style → component definitions
- elements stable in role but varying in value → component properties
- elements present in some documents only → variants, plus optional slots
- elements unique to one document → instances, deliberately not generalized

One document still works. It just yields a weaker model, and the report says which
conclusions rest on a single observation.

## When the document has a generator

A PDF produced by a reporting library (ReportLab, wkhtmltopdf, a headless browser)
was laid out by code that still exists somewhere. If that code is reachable,
reverse-engineering its output is the harder route to information the generator
already holds exactly — positions, colors and structure, with no inference and no
tolerance.

This is why input is an interface rather than a PDF parser. Two extractors, one
IR, one downstream pipeline:

- `PdfExtractor` — the general case, and the reason this tool is useful publicly:
  it works on documents whose origin you do not control.
- `GeneratorExtractor` — reads a layout specification directly. Exact by
  construction, so `normalize` needs no geometric tolerance and the repair loop
  has almost nothing to repair.

Both feed the same verification: rendering the PDF as ground truth and diffing
against it stays valid regardless of where the IR came from.

## Anti-coupling rules

These are requirements, not aspirations; a violation is a bug.

1. No domain vocabulary in engine code — no chart types, no business terms.
2. No hex literals, no magic sizes. Values come from the document.
3. Profiles are data, supplied by the user. Shipped profiles are examples only.
4. Core code never touches the filesystem; it takes bytes and returns objects.
   Only the CLI does I/O.
5. No absolute paths and no source filenames in any artifact — extracts are
   shareable without leaking where they came from.
6. No network access and no credentials in the default path.

## Open questions

`probe` answers the first group per document, not once for the project — a
different source PDF can change every one of them:

- Are fonts embedded, subsetted, repairable, or already on the system?
- Is the source sRGB? A CMYK or Separation source caps color accuracy before the
  rebuild starts.
- How many nodes does a text-to-outline page produce, and where does Figma begin
  to degrade? Observed so far: a dense infographic page converts to roughly
  400–800 paths plus 1700–2700 glyph outline references, which is why vector
  import is per-region and never per-page.
- Are there clip paths, masks, gradients, patterns or transparency? A document
  with none of them is the best case for fidelity and removes whole classes of
  translation risk.

Answered by S3, on one class of document:

- **The ceiling is roughly 96%** at a strict threshold and 98.8% at a tolerant
  one, for a dense infographic page with flat fills and outlined text. All of the
  difference is edge antialiasing; fills and positions matched exactly. Details
  in [`../figma-plugin/README.md`](../figma-plugin/README.md#observed-ceiling).
- **`createNodeFromSvg` reproduces geometry and color exactly** for a document
  without clip paths, masks, gradients or transparency. Whether it survives those
  features is still untested.

Still genuinely open:

- Do text-heavy pages (tables) and chart-heavy pages have materially different
  ceilings? Only one page has been measured.
- Does a built page — live text in an installed font rather than outlines — reach
  the same ceiling, or does font rasterization cost more than glyph outlines do?
- *(unverified)* Whether exporting the built tree back to IR is precise enough
  for structural diffing, or whether the plugin must record provenance as it
  builds.
- Undecided: region segmentation — derived from clustering, or declared in the
  profile.
