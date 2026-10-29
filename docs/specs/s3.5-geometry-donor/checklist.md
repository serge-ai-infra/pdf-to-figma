# S3.5 — Acceptance checklist

Fixed at planning time. A stage is done when every box is checked against a
real run, not when the code exists. Items that turn out to be wrong get
struck through with a reason — never quietly rewritten to match what was
built.

Verified against a real third-party document (kept out of the repo) and 18 new tests (15 pure fixture
tests + 3 real-poppler integration tests). `pytest`, `ruff`, `mypy --strict`,
`tsc --noEmit` all clean. An adversarial review pass on the full diff found
and fixed six real issues before this was called done (see Engineering) —
none changed the real-document output (byte-identical `donors.json` before
and after). What's left needs Figma Desktop, which wasn't available at the
time — see the two unchecked items below.

## Crop correctness

- [x] `pdftocairo -svg -x/-y/-W/-H` confirmed to leave vector output at full
      page size — tested directly against the real PDF (612×792pt in, same
      out, regardless of the crop flags); `-pdf` output does the same
- [x] A path entirely inside the target bbox survives the crop
- [x] A path entirely outside the target bbox is dropped
- [x] A path straddling the bbox edge survives (intersection, not
      containment — see spec's Risks)
- [x] A path under a `matrix(...)` transform is bbox-tested in *transformed*
      (page) space, not its raw `d` coordinates
- [x] Every `<use>` element is dropped, unconditionally, regardless of
      whether its glyph anchor falls inside the bbox
- [x] `<defs>` is kept when a surviving element references it (including
      transitively — a defs entry referenced by another kept defs entry),
      dropped when nothing does
- [x] Root `<svg>` of the output has `viewBox`/`width`/`height` set to the
      target bbox, in points, not the source page's

## CLI

- [x] `pdf2figma convert donor <pdf> <ir> --ids a,b -o donors.json` produces
      `{convert_version, nodes: [{id, bbox, svg}]}` for exactly the
      requested ids, in the order given — real run: 3 ids
- [x] An id naming a `rect`/`ellipse`/`line`/`text` node is a CLI error, not
      a silent skip or a wrong-shaped entry (exit 2, real run against a
      `rect` id from a real IR)
- [x] An id absent from the page is a CLI error, not a silent skip (exit 2,
      real run)
- [x] `pdf2figma convert donor --help` documents every flag
- [x] **Revised, against real data**: `--ids` is optional; omitted, every
      `path`-kind node on the page is selected — real run against
      one real page (real third-party PDF, real IR): well over a hundred
      `path` nodes, one donor each, `donors.json` produced in under 2s. The original "explicit `--ids` only, no automatic
      selection" design didn't survive contact with a real report's actual
      path count — struck through in the spec, not silently rewritten.
- [ ] **`--page` on a real multi-page document, end to end through the CLI
      subcommand** — `page_to_svg`'s own page-selection is covered by a real
      poppler integration test (page 2 of 3), but `convert donor` itself was
      only exercised against page 1 of a single-page
      document. The `--page` plumbing is the same
      `_load_ir_page` helper every other page-scoped command already uses,
      so this is a low-risk gap, not an unknown — just not independently run.

## Plugin panel

- [x] `tsc --noEmit` and `npm run build` clean
- [x] **Panel 5 imports a `donors.json` into a real live Figma file** — done
      for real: all donors for one real report page, imported via
      Figma's web client. `createNodeFromSvg`/resize/position/
      `sourceNodeId` all confirmed working by the resulting `verify
      structural` run below. **Does not overturn `architecture.md`'s
      Desktop requirement** — a premature read at the time: the
      web client's dev-plugin load didn't survive a reload
      (`web:getLocalFileExtensionSource` / "Unknown plugin" — the browser
      loses its handle on the local `manifest.json` across reloads in a way
      Desktop's native file access doesn't), so re-verifying the z-order
      fix below needed a fresh "Import plugin from manifest" in the same
      tab. Consistent with Desktop being the reliable path, not a
      counter-example to it.
      **Found by this real run, not anticipated**: the first version
      (`appendChild`) buried a `liveText` label under a donor's background
      path — invisible in a screenshot, invisible to `verify structural`
      too (it checks each node's own properties, not what's drawn over it).
      Root-caused via the two nodes' own `z` in `doc.ir.json` (background
      `z` far below the label's — background should paint first, didn't). Fixed
      with `insertChild` at an increasing index (spec's Plugin panel
      section has the detail); `tsc`/build re-confirmed clean after the
      fix. **Re-verifying the fix itself against a fresh re-import is the
      one thing still pending** — the diagnosis and the code change are
      done, the closing loop (re-import with the fixed `code.js`, re-export,
      re-check that label specifically) hadn't happened as of this write-up.

## Integration with existing verify — the point of this stage

- [x] Zero changes to `emitter/src/payload.ts`, `src/pdf2figma/verify/
      model.py`, or `structural.py` — confirmed by diff: this stage touched
      `src/pdf2figma/convert/`, `cli.py`, `figma-plugin/src/code.ts`,
      `ui.html`, tests, and docs, nothing in either model
- [x] After importing a donor and running `verify structural`, the donor's
      source-IR id shows up as `matched` or `mismatched` — not `missing` —
      confirming the tag round-trips through a real export. Real run,
      one real report page, all donors imported: `213 matched, 107
      mismatched, 5 missing, 0 extra` — donors themselves contribute 0 to
      `missing`/`extra`; the 107 `mismatched` and remaining 5 `missing` are
      pre-existing gaps this stage was never meant to close (structural
      fidelity of a multi-path donor is the spec's own documented
      non-goal), not a donor-import regression.

## Real run

- [x] `convert donor` run against a real IR +
      the real source PDF, for three real `path` regions (three
      donut-chart cards),
      producing a non-empty `donors.json` (a few KB of SVG each)
- [x] The resulting SVG rasterized (Quick Look, no Figma involved) and
      visually compared against a `pdftoppm`-cropped reference of the same
      bbox: donut ring, card outline, header bar and legend swatches all
      present, correctly positioned and colored, zero text ghosting
- [ ] Manual, in Figma Desktop: the same donor imported via panel 5, visibly
      aligned with the rest of the build at its bbox position — the other
      half of the blocked item above

## Engineering

- [x] `ruff check` and `mypy --strict` clean on `src/pdf2figma/convert/`
      (and the rest of `src`/`tests` — full-repo run, not just the new files)
- [x] 18 new tests pass (15 in `test_convert_donor.py`, hand-built SVG
      fixtures, no real PDF, no poppler; 3 in `test_convert_poppler.py`,
      real `pdftocairo` process, skips cleanly when it's missing) — 143
      total, up from 125
- [x] Adversarial self-review against the full diff,
      fixes applied and re-verified (tests, ruff, mypy, tsc all still clean;
      real-document output unchanged byte-for-byte): `applyShapeStyle`/
      `applyInstanceStyle` now explicitly clear fill/stroke when the payload
      doesn't carry one instead of leaving a reused instance's stale value
      (the same mismatched-fill/stroke bug class the other fix
      addressed, just for the falsy case); `crop_to_donor`'s XML parse
      failure now surfaces as a clean CLI error instead of a raw traceback;
      re-importing a donor id replaces rather than duplicates the tagged
      node; `_referenced_ids` catches every `url(#id)` in an attribute value
      instead of only the first; `_path_bbox` no longer corrupts a
      scientific-notation coordinate by stripping its exponent marker along
      with path commands; `page_to_svg` has a timeout so a pathological PDF
      can't hang the CLI forever. Two findings reviewed and deliberately not
      changed: the font-suffix set (`extract/pdf.py`) misses TrueType/Office
      composite names, but the real corpus used is 100%
      Standard-14 (verified: every text node across the corpus
      is Helvetica/ZapfDingbats/Symbol) and stripping just the suffix
      wouldn't fully fix the TrueType case anyway (the base family name
      itself often needs normalizing too, e.g. `TimesNewRomanPS` →
      `Times New Roman`) — a half-fix that would look done without being
      done; and `exportNode`'s single-fill read for a multi-path donor is
      the structural non-goal the spec already documents, not new scope.
- [x] No new Python dependency — `xml.etree.ElementTree` and `subprocess`
      are stdlib
- [x] `test_privacy.py`'s filesystem-purity check extended to
      `convert.donor`/`convert.poppler` — both pass (neither imports
      `pathlib` or calls builtin `open`)
- [x] `README.md` documents the CLI command, panel 5, and the run-order
      caveat (donor import after Build, before Export built IR)
- [x] `docs/architecture.md`'s stack section updated: poppler is no longer
      invoked by `probe` only

## Explicitly not in S3.5

Listed so their absence is not mistaken for an oversight: a size-based
threshold within "every path-kind node" (still none — see the revised CLI
default above, which is "all of them," not a cutoff), importing text glyphs
inside a donor crop, gradient/pattern/clip-path correctness against a real
document that has them (untested — the fixture tests exercise the *logic*,
not a real gradient-bearing PDF), structural fill/stroke scoring tuned for
multi-path donors, applying this to any shape kind other than `path`, and
(this pass specifically) the Figma Desktop half of verification — written,
typechecked, not yet run.
