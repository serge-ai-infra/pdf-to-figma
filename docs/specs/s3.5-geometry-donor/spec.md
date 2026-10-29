# S3.5 — Geometry donor

Sits between S3 (plugin skeleton, which proved `createNodeFromSvg` works at
all) and S4 (emit and build, which established the payload/plugin contract).
`architecture.md`'s "What import is for" names *geometry donor* as one of
import's two jobs — "Donuts, gauges and custom curves are inherited rather
than generated" — but nothing implements it: `shapeToPayload`
(`emitter/src/payload.ts`) returns `unsupportedPayload(node.id,
"path-geometry-unavailable")` for every `path`-kind shape and stops there.
Real repair-triage runs against a small corpus surfaced this as the single
largest `missing` pattern — bigger than either bug already fixed. This stage closes it.

## Goal

`pdf2figma convert donor <pdf> <ir.json> --ids p0.c12,p0.c15 -o donors.json`
produces `[{id, svg, bbox}]` — one cropped, geometry-only SVG per named
`path`-kind IR node, in the node's own bbox. A new plugin panel imports each
one with `figma.createNodeFromSvg`, positions it at `bbox * PT_TO_PX` (the
same conversion every other node already uses), and tags it
`setPluginData("sourceNodeId", id)` before dropping it into the existing
`pdf2figma build` frame.

That tag is the entire integration point. `exportNode()`
(`figma-plugin/src/code.ts`) already walks every child of the build frame
and picks up anything carrying `sourceNodeId` — it doesn't care whether the
child came from `buildComponentInstance`, `buildPlainNode`, or (new) a donor
import. **No change to `payload.ts`, `verify/model.py`, or the structural
diff is needed.** A donor becomes a `matched` or `mismatched` region in
`pdf2figma verify structural` for free, the same way a plain rect does.

## Non-goals

- ~~**Automatic region selection.** No size threshold picks which `path`
  regions get donor treatment... that judgment call is the operator's, made
  once per document by eye against the IR, and handed to the tool as an
  explicit `--ids` list.~~ **Revised against real data**: a real report page
  has ~10 `rect` and well over a hundred `path` nodes (measured on one real
  page) — every rounded-corner bar, donut
  and section-header strip a PDF draws with curves rather than a plain `re`
  rectangle lands here. Curating that by hand doesn't scale to an actual
  product; `--ids` omitted now means *every* `path`-kind node on the page,
  no filtering, no size cutoff invented (still consistent with anti-coupling
  rule 2 — "no magic sizes" — this isn't a threshold, it's "all of them").
  `--ids` stays for the scoped/ad-hoc case (`repair crops`'s own interface,
  still useful for testing one region), but is no longer the only way in.
- **Text inside a donor's crop.** Every `<use>` element in a page's SVG
  conversion is a text glyph reference (verified on a real document:
  thousands of `<use>`, 0 `<rect>`/`<circle>`/native shapes, roughly a
  hundred top-level `<path>` —
  cairo draws all geometry as paths and all text as glyph `<use>`s). S4
  already emits live text for every `text`-kind IR node in the same region.
  Importing outlined glyphs too would draw a dead copy of that text
  underneath the live one. This stage drops every `<use>`, unconditionally —
  a donor is geometry only, by construction, not by cropping luck.
- **Gradients, patterns, clip paths inside a donor.** `<defs>` is kept
  verbatim (cheap — an unreferenced `<defs>` entry costs nothing and SVG
  doesn't render it), so a document that has them isn't actively broken, but
  nothing here is tested against one. `architecture.md`'s own open-questions
  list already flags this as untested for straight SVG import; a donor crop
  doesn't remove that gap, it inherits it.
- **Structural fidelity scoring for donor regions.** A donor is typically
  several original PDF path *objects* merged into one cropped SVG (the
  reference region below is 15 kept `<path>` elements — outline, wedges,
  legend swatches — under one `id`). `exportNode`'s `visualNode()` reads
  a single child's single fill; there is no one fill to read. Structural
  `mismatched:fill` noise on a donor region is expected and uninformative —
  the perceptual diff (S5) is the real fidelity signal here, not structural.
  Making `exportNode` multi-child-aware is future work with no case to test
  it against yet.
- **Fixing this for `rect`/`ellipse`/`line` shapes.** Those already build as
  real Figma nodes (S4). Donor import exists only for `path`, the one kind
  S1's classifier deliberately leaves geometry-less.

## What actually works, verified against a real document

`architecture.md` proposed cropping via poppler flags: "`pdftocairo -svg`
supports `-x/-y/-W/-H`... translate bbox from PDF points to pixels." Tested
directly against a real report's source PDF — **it doesn't work**.
`pdftocairo -svg -x 100 -y 500 -W 800 -H 700 -r 300` produces a full
612×792pt page, `viewBox="0 0 612 792"`, unchanged. Same result for `-pdf`
output. The same flags against `-png`/`pdftoppm` crop exactly as documented
(confirmed: 800×700px out of a 2550×3300px page). **Poppler's crop flags are
raster-only; vector output formats (svg, pdf, ps) ignore them silently, with
no warning.** This is exactly the kind of thing `architecture.md` flags as
"unverified" until a probe checks it — now checked, and the answer changes
the design.

The mechanism that does work, verified against the same document and a real
region (a donut-chart card):

1. Convert the whole page to SVG once — `pdftocairo -svg`, stdin/stdout
   pipes, no temp files (`convert/poppler.py::page_to_svg`).
2. Parse it; keep only top-level `<path>` elements (skip `<defs>`) whose
   bbox intersects the target region. Cairo bakes each element's transform
   into a `matrix(...)` on the element itself rather than once on the root —
   header-bar-style paths carry `matrix(1,0,0,-1,0,792)` (PDF's bottom-up
   space, flipped), text-adjacent shape paths carry none (already top-down)
   — so bbox has to resolve each path's own transform, not assume one
   convention (`convert/donor.py::crop_to_donor`).
3. Drop every `<use>` (see non-goals).
4. Keep `<defs>` verbatim if anything kept still references it (a stroke
   pattern, a gradient); drop it otherwise — it's dead weight, not incorrect
   to keep, but no reason to bloat the file when nothing points to it.
5. Rewrite the root `<svg>` to `viewBox="{x} {y} {w} {h}"`,
   `width="{w}pt"`, `height="{h}pt"` — the target bbox, in the same point
   units cairo already emits. No pt→px conversion here; that stays the
   plugin's job (below), matching every other artifact this project hands
   to TypeScript.

Rasterizing the result (`qlmanage -t`, no Figma involved) against the same
region cropped with `pdftoppm -x/-y/-W/-H` (which *does* crop, raster) as a
reference: donut ring, card outline, header bar, legend swatches — all
present, positioned and colored correctly, zero glyph ghosting. Every
page-level path outside the region dropped as expected.

## Boundary: where this can and can't be pure

`architecture.md` rule 4: "Core code never touches the filesystem; it takes
bytes and returns objects. Only the CLI does I/O." `convert/donor.py` keeps
that exactly — a pure string/XML transform, `(page_svg: str, bbox: BBox) ->
str`, tested with hand-built SVG fixtures the same way `tests/fixtures/
synthetic.py` hand-builds PDFs.

`convert/poppler.py::page_to_svg` is the one new exception, and it's
narrower than it looks: it spawns `pdftocairo` over `stdin`/`stdout` pipes —
bytes in, string out, no path ever touches disk. It doesn't open a file and
doesn't import `pathlib`, so it satisfies `test_privacy.py`'s actual
assertion even though it isn't "pure Python." This is the same shape
`verify/perceptual.py::load_rgb` already established for images (a `Path`
in, an array out) — S5 already accepted that boundary-crossing modules don't
have to route through `cli.py` when the I/O is a real external resource, not
a privacy-sensitive source path. Poppler itself was already a project
dependency (`README.md` requirements, `scripts/probe-pdf.sh`); this is the
first stage to call it from Python rather than a shell script, so
`architecture.md`'s stack section ("invoked as external binaries by `probe`
only") needs updating to match — the license reasoning (execution, not
linking) is unchanged, only which caller does the executing.

## CLI

```
pdf2figma convert donor <pdf> <ir.json> [--ids p0.c12,p0.c15] \
  [--page 1] -o donors.json [--pretty]
```

- `<pdf>` — read as bytes, same as `extract`.
- `<ir.json>` — supplies each id's bbox and confirms it's a `shape` node with
  `shape == "path"`; a `rect`/`ellipse`/`line`/`text` id, or an id absent
  from the page, is a CLI error (exit 2), not a silently-skipped entry —
  matching `verify structural`'s existing style of failing loud on a bad
  input file rather than producing a partial report. This check still
  applies when `--ids` is given explicitly; it's moot for the default case,
  which only ever selects real `path`-kind ids in the first place.
- `--ids` — optional, comma-separated, same style as `repair crops`. Omitted
  (the expected case for a full document, per the revised non-goal above):
  every `path`-kind node on the page. A page with none is a CLI error, not
  an empty-but-successful output — the same "loud, not silent" posture.
- `--page` — 1-based, default 1, same as every other page-scoped command.
- Output: `{convert_version, nodes: [{id, bbox: {x,y,w,h}, svg}]}`, bbox in
  points. Not a `Payload` — a sibling artifact the plugin reads through its
  own panel, not through `buildFromPayload` — but versioned the same way
  every other cross-language artifact here is (`payload_version`,
  `built_version`, ...), so an incompatible `donors.json` is a loud plugin
  error instead of a silent partial import.

## Plugin panel

Panel 5, "Import geometry donors" (`ui.html`), picking a `donors.json`:

- For each entry: `figma.createNodeFromSvg(svg)`, resize to
  `bbox.w * PT_TO_PX × bbox.h * PT_TO_PX`, position at
  `bbox.x * PT_TO_PX, bbox.y * PT_TO_PX` (`PT_TO_PX = 4/3`, the same constant
  `exportNode` already defines) — explicit, not trusted from the SVG's own
  declared size, the same defensiveness every other imported/created node in
  `code.ts` already gets.
- `setPluginData("sourceNodeId", entry.id)`, then **inserted behind**
  whatever's already in the `pdf2figma build` frame (`BUILD_FRAME_NAME`) —
  found via a new `findBuildFrame()` that does **not** clear children,
  unlike `ensureBuildFrame()` (used only by `buildFromPayload`). Donor
  import never creates the frame itself, and errors if the frame doesn't
  exist yet.
  **Found on a real document, not anticipated in design**: a donor is
  routinely a background/decorative path (a card panel, a donut) that the
  source PDF paints at a low `z`, with a `liveText` label painted over it
  afterward at a much higher `z` (measured: a card background painted
  well over a hundred objects before its own legend label). `appendChild`
  — the first implementation — placed
  every donor on top of everything Build had already placed, silently
  burying that label under the card background. `verify structural` didn't
  catch it: comparing each tagged node's own properties says nothing about
  what's drawn in front of it, so the buried label still reported
  `matched`. Fixed by `insertChild` at an increasing index from 0 (confirmed
  against the plugin typings: index 0 is bottom-most paint order, not
  "first created") — every donor in a batch lands behind every
  pre-existing child, in the donors' own relative order among themselves.
- **Run order matters and isn't enforced by panel position.** Panel 3
  (Build) clears and rebuilds the frame every run — a donor imported before
  a later Build disappears. Donor import must run *after* the Build it's
  meant to sit alongside, and *before* Export built IR (panel 4) if the
  donor's supposed to show up in the structural diff. The panel is
  numbered 5 (appended, not inserted, so panels 1-4 keep their existing
  numbers) but documented as an out-of-numeric-order step in both `ui.html`'s
  own hint text and `README.md`.

## Verification

- `convert/donor.py`: hand-built SVG fixtures (a handful of `<path>`s with
  and without a `matrix(...)` transform, a `<use>`, a `<defs>` block),
  asserting which paths survive a given crop bbox, that `<use>` never
  survives, and that `<defs>` is dropped when nothing kept references it.
  No real PDF, no poppler, no I/O.
- `convert/poppler.py`: one integration test, skipped when `pdftocairo` isn't
  on `PATH` (`shutil.which`), using `tests/fixtures/synthetic.py::build_pdf`
  to confirm `page_to_svg` returns a well-formed SVG at the page's own
  dimensions — the same "cross-check against an independent converter"
  posture S1 already established, not a new one.
- Manual, against a real document (no way around it, `pdftocairo` isn't
  mocked and Figma Desktop has no headless mode): `convert donor` against
  a real IR for a real chart region, panel 5 in
  Figma Desktop, confirm the imported node's geometry lines up with the
  region visually and that a subsequent `verify structural` run picks it up
  as a region (whatever its classification — `matched` bbox with noisy
  `fill` is expected, per the structural non-goal above).

## Risks

- **`<path>`-only extraction is cairo's-output-shaped, not SVG-shaped.**
  A future poppler version, or `-svg` against a document using native
  `<rect>`/`<circle>`, would silently drop those elements — this stage
  targets what `pdftocairo -svg` actually emits today (confirmed 0 native
  shape elements, 100% path, across the one real document tested), not the
  SVG spec's full element set. If that assumption breaks, donors go quietly
  empty rather than erroring — worth a follow-up assertion if it's ever hit.
- **One document tested.** The `matrix(...)`-transform handling, the
  drop-versus-keep `<defs>` logic, and the visual crop check are all
  verified against one real document only. The rest of the corpus
  probably shares this behavior, but that's an inference, not a second measurement.
- **Bbox intersection, not containment.** A path straddling the region
  boundary is kept whole, uncropped to the exact rectangle — the donut
  card's rounded corners are already fully inside their own bbox in the
  tested case, so this hasn't been exercised against a path that genuinely
  crosses the edge. Keeping too much (a sliver of a neighboring element)
  is the safer failure than dropping part of the target shape, but it's an
  explicit choice, not a proven-safe one.
- **"Every donor behind every pre-existing child" is a heuristic, not true
  z-ordering.** It's correct for the case actually observed — decorative
  path geometry painted early, labels painted late — but says nothing about
  a document where a `path` genuinely belongs *in front of* some other
  built content by the source PDF's own paint order. Getting that right in
  general means carrying each built node's own `z` through to something the
  plugin can compare at import time, which nothing currently does (payload
  nodes carry no `z` either). Not attempted here — the blunt fix matches
  every case seen so far; a document that contradicts it hasn't turned up.
