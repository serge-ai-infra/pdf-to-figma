# Figma plugin

Four things: imports vector (S3), exports raster back out (S3), builds a
payload into components and nodes (S4), and exports the built tree back into
IR-shaped data for verification (S5). S3's panels exist to measure the
ceiling, not to build anything — S4's panel is the actual build step, and
S5's panel is what makes that build checkable.

## Why a plugin at all

Figma has no PDF import, and the REST API cannot create nodes. Building inside a
Figma file is only possible from a plugin, which means an open document and a
click. Everything before and after that click automates; the click itself never
will.

## Install (Figma Desktop, once)

1. `npm install && npm run build` in this directory — compiles `src/code.ts`
   to `code.js`, which is what the manifest actually loads. Re-run
   `npm run build` after pulling any change to `src/code.ts`.
2. Open Figma **Desktop**. The browser can load a development plugin, but loses
   it on reload, so Desktop is the dependable path.
3. Menu → **Plugins → Development → Import plugin from manifest…**
4. Pick `figma-plugin/manifest.json` from this repository.

It now appears under Plugins → Development → *pdf-to-figma*.

## Measuring the ceiling

```bash
# 1. reference render and vector conversion of the same page
./scripts/probe-pdf.sh report.pdf work/probe 200

# 2. in Figma: run the plugin, import work/probe/svg/page-1.svg,
#    keep it selected, export at 200 dpi (matching step 1)

# 3. compare — the export lands in ~/Downloads
.venv/bin/python scripts/compare-images.py \
    work/probe/png/page-1.png \
    ~/Downloads/page-1@200dpi.png \
    -o work/probe/ceiling-diff.png
```

The resulting percentage is the **ceiling**: the best any rebuild of this page
can score, given that two different rendering engines are involved. A later build
scoring below it has our bugs in it; scoring above it is not possible.

Run it per page. A text-heavy page and a chart-heavy page have different
ceilings, and averaging them hides both.

### Observed ceiling

A dense single-page infographic — flat fills, no gradients, no transparency,
standard-14 fonts, text converted to outlines — measured at 200 dpi:

```
threshold   8/255 → 96.05% matching
threshold  16/255 → 96.69%
threshold  32/255 → 97.77%
threshold  64/255 → 98.78%
threshold 128/255 → 99.78%
```

The difference map showed **only outlines**: glyph edges and shape borders. Every
large fill matched exactly, and nothing was displaced or miscolored.

The shape of that curve is the useful part. A smooth climb with rising threshold
means the differences are antialiasing — two rasterizers disagreeing at edges. A
structural fault behaves the opposite way: a displaced or miscolored region
differs at full amplitude and stays visible no matter how high the threshold
goes.

Practical consequence for S5: score fidelity at a threshold around 32–64, or mask
edge pixels before comparing. Chasing the last 4% at threshold 8 means chasing
someone else's rasterizer.

## Why DPI has to match, and why the scale is dpi/96

Figma imports SVG as **CSS pixels, not points**. CSS defines one point as 4/3px
at 96dpi, so a 612×792pt page arrives as an 816×1056 frame. Exporting at `dpi/72`
therefore overshoots by exactly 4/3 — measured, not theorized: it produced
2267×2934 against a 1700×2200 reference.

The plugin exports at `dpi / 96`. At 200 dpi a letter page then comes out
1700×2200 px from both `pdftoppm` and Figma.

This also matters beyond export: geometry inside Figma is 4/3 larger than the
source points, so anything the builder emits in S4 has to use the same unit as
the imported reference, or the two will never overlay.

The comparator refuses mismatched sizes rather than rescaling — resampling would
smear exactly the differences being measured.

## Known limits: import/export (S3)

- Text arrives as glyph outlines via SVG import, so it is pixel-accurate and
  not editable. Live text comes from the build step (S4) instead, never from
  SVG.
- Figma ignores `@font-face` in imported SVG. Any SVG carrying real text nodes
  will render in a substituted font.
- A full page is thousands of nodes. Fine as a reference, too heavy as a working
  layer — the build step imports structured data instead, not vector.

## Building from a payload (S4)

Panel 3 reads a `*.payload.json` from `emitter` (see the root README's
"Emitting a payload") and builds it — every matching and profile decision was
already made there; this side is mechanical:

- A **"Components" page** holds every component master, created once and never
  cleared. A master is tagged with `setPluginData('candidateId', id)`; a
  rebuild searches for that tag before creating a new one, so re-running
  updates the master in place rather than duplicating it.
- A single **build frame**, named `pdf2figma build`, is cleared and rebuilt on
  every run — components survive; nothing inside this frame is safe to
  hand-edit between builds.
- A node whose font can't be loaded (`figma.loadFontAsync` fails) is skipped
  and counted, never rendered in a substituted font pretending to be the real
  one. Same treatment for `path`- and `image`-kind nodes, which carry no
  geometry or pixel data at all — nothing to build regardless of matching.

### Known limits: building (S4)

- **One document's build frame per file, this pass.** `payload.json` carries
  no filename (privacy, same as the IR), so there's no per-document key to
  frame on. Building a second document into the same file overwrites the
  first's build frame.
- **No Figma Variables, no variants, no auto layout.** Literal values,
  single-state components, absolute positions — see
  `docs/specs/s4-emit-build/spec.md` for why each is out this pass.
- **Only component masters are idempotent.** Instances are rebuilt fresh
  inside the cleared build frame every run; a hand-made tweak to one instance
  doesn't survive a rebuild.
- **No headless verification.** There's no way to script Figma Desktop, so
  this side of S4 is checked by hand, not by a test suite — see the
  checklist's split between automated (`emitter`) and manual (this panel)
  verification.

## Exporting built IR (S5)

Panel 4 is the counterpart to panel 3, in the other direction: it reads the
build frame's direct children — each tagged with `sourceNodeId` when panel 3
built it — and reconstructs, per node, `id`, `bbox` (px→pt, ÷4/3, the exact
inverse of the payload's own conversion), fill/stroke and, for text, the
font and characters. Downloads `build.built.json` through the same
Blob-download path panels 2 and 3 already use — still no filesystem access,
still nothing sent anywhere.

Feeds `pdf2figma verify structural` (see the root README's "Verifying a
build"). A node the build frame skipped — an unloadable font, a `path`- or
`image`-kind one-off — simply has no entry here, which structural diff
reports as `missing`. This panel doesn't know or care why a node is absent;
it only reports what it can actually read off the live document.

### Known limits: exporting (S5)

- **Untagged nodes are silently excluded, not guessed at.** Anything in the
  build frame without a `sourceNodeId` (hand-added, or built by a version of
  the plugin from before this tag existed) is skipped and counted, never
  included with a fabricated id.
- **Reads the current page's build frame only.** If you've built more than
  one document into the same file (against this stage's own advice — see
  S4's "one document's build frame per file" limit above), this exports
  whichever one currently occupies `pdf2figma build`.
