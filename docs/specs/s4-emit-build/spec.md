# S4 — Emit and build

Turn one document's IR, an Inventory built from its corpus, and an optional
profile into Figma nodes — components for what recurs, plain nodes for what
doesn't, idempotent on the component masters.

This is where TypeScript enters the project. `docs/architecture.md`'s stack
section already commits to it ("Python writes JSON, TypeScript reads it"), and
S3's `code.js` said so directly: *"TypeScript arrives in S4, when there is
enough logic to earn it."* There is, now.

## Goal

`emit` (new, `emitter/`) turns `document.ir.json` + `corpus.inventory.json` +
an optional `profile.json` into `document.payload.json`. The Figma plugin's
new **Build** action turns that payload into nodes in the current file: a
component + instance for every node that matches an Inventory candidate, a
plain node for everything that doesn't, positioned absolutely at the node's
own geometry. Re-running updates component masters in place instead of
duplicating them.

## Non-goals

Explicitly out of this stage, so their absence isn't mistaken for an
oversight:

- **Variables.** Figma Variables (bound fills, bound sizes) are real work —
  collections, modes, binding — and nothing here needs them to prove the
  pipeline end to end. Literal values only, this pass.
- **Variants.** A Figma variant needs a variant *axis*, and S2 deliberately
  never produces one — it clusters atoms, not the multi-node composites
  ("cards") that would carry a state like `withBadge: true/false`. There is
  nothing to build a variant from yet. One component per candidate, no
  properties.
- **Auto layout.** Every node is placed at its own absolute position (the IR's
  own bbox, scaled to Figma's pixel space). Inferring rows/columns/padding
  from repeated gaps is a real layout-inference problem in its own right, not
  attempted here even though S2's spacing tokens would be a natural input to
  it later.
- **Per-instance idempotency.** Only *component masters* are found-or-created
  idempotently, tagged with `candidateId` via plugin data. Instances are
  rebuilt fresh inside a cleared frame on every run — matching "is this the
  same instance as last time" across a changed document is a harder problem
  deferred until it's actually needed.
- **Image and path reconstruction.** `ImageNode` carries no image bytes (never
  extracted, out of scope since S1) and `path`-kind shapes carry no raw
  contour (only a bbox, per S1's classifier). Neither can be faked with a
  placeholder box without becoming a wrong answer that looks like a right one
  — both are skipped and reported, the same "vague is cheaper than wrong"
  stance S1 already took for ambiguous shape classification.
- **Font repair.** Live text is attempted only for a font Figma can already
  load (`figma.loadFontAsync` succeeds — typically the standard-14 fonts
  already on the system). A font that fails to load is skipped and reported,
  never faked with a substituted font pretending to be the real one.

## Stack

TypeScript, two independent Node projects, no shared build tooling:

- **`emitter/`** — no Figma API, runs anywhere Node runs. `typescript` is the
  only dependency; tests use `node:test` (built into Node, zero additional
  dependency), matching the project's existing reluctance to add libraries a
  hand-rolled implementation covers adequately (see S2's clustering).
- **`figma-plugin/`** — gains `src/code.ts`, compiled to `code.js` (now a
  build artifact, gitignored, the same way S1's Python build artifacts are).
  `@figma/plugin-typings` (MIT) is the one new dependency, for typing the
  Figma Plugin API — nothing else.

## The boundary that keeps this testable

Every matching and profile decision happens in `emitter/`, which has no Figma
API and is fully unit-testable. `payload.json` is the finished decision — the
plugin reads it and acts, but never matches a node to a candidate and never
looks at a profile. This mirrors S1's own rule (core logic never touches the
filesystem, only the CLI does); here the boundary is "core logic never calls
the Figma API, only the plugin does." The plugin side calls a real API that
has no headless test runner — architecture.md is explicit that "the build
step requires Figma Desktop. Headless is impossible" — so pushing every
testable decision to the other side of that boundary is what makes most of
this stage verifiable at all.

## Emitter

```
emitter/src/
  ir.ts          types mirroring src/pdf2figma/ir/model.py
  inventory.ts   types mirroring src/pdf2figma/inventory/model.py
  profile.ts     Profile type, DEFAULT_PROFILE_ENTRY
  match.ts        pure: nearest color/size, candidate resolution
  payload.ts      pure: buildPayload(ir, inventory, profile) -> Payload
  cli.ts          the only I/O: reads 3 JSON files, writes payload.json
```

**Matching** (`match.ts`) reuses Inventory's own tolerances rather than
re-deriving anything: nearest `ColorToken` within `tolerances.color`, nearest
`SizeToken` (same family/weight/italic) within `tolerances.size`. A node
matches a `ShapeCandidate`/`TextCandidate` when its resolved signature equals
one; otherwise `candidateId: null` — architecture.md's "instance, deliberately
not generalized," never a guessed match.

**Profile** (`profile.ts`) is minimal, data the user supplies (rule 3 of
architecture.md's anti-coupling list — "profiles are data... shipped profiles
are examples only"):

```json
{
  "candidates": { "shape-0": { "name": "card", "component": true } },
  "defaults": { "component": false, "liveText": false }
}
```

An unmatched node, or a matched candidate absent from `profile.candidates`,
falls back to `defaults`. `emitter/example.profile.json` ships as a checked-in
example only, never read by default — the same discipline S2 applied to its
own tolerance defaults ("unvalidated, not calibrated").

**Payload** (`payload.ts`) does the pt→px conversion exactly once, here, per
architecture.md: "Figma is not in points... the conversion happens once, in
the emitter." Scale is ×4/3 (Figma imports at CSS pixels, where one point is
4/3px — the same ratio S3 measured and documented in `figma-plugin/README.md`).
Each payload node: `id, kind, candidateId, component, liveText, name, bbox`
(px), style (`fill`, `stroke`, `font`), `text`.

**Privacy**, carried forward unchanged: `cli.ts` is the only file touching
`fs`/`path`; a source-scan test (mirroring `tests/test_ir.py`/`test_privacy.py`)
asserts `match.ts`/`payload.ts` never do. No absolute path or source filename
anywhere in `payload.json`.

## Plugin build step

Purely mechanical — every decision was already made by `emitter/`:

- A "Components" page holds every master, created once and never cleared.
- A rebuildable frame per document: found by name or created, its children
  cleared and rebuilt every run, resized to `payload.page`.
- Per payload node:
  - `component: true` with a `candidateId` — find an existing master on
    "Components" via `getPluginData('candidateId') === candidateId`; create
    one if missing (tagged immediately with `setPluginData`); `createInstance()`,
    position and resize into the build frame. Text: `loadFontAsync` before
    setting `.characters`; a failure leaves the master's own text and logs a
    skip rather than throwing.
  - otherwise — a plain node from the payload's own `kind`: `rect` →
    `createRectangle`, `ellipse` → `createEllipse`, `line` → `createLine`,
    `text` → `createText` (same font-load-or-skip rule). `path` and `image`
    kinds are skipped and counted, never faked.
- Status is reported through the same `say()` pattern S3 already uses:
  components created vs. matched-existing, instances, plain nodes, skips.
- **One document's build frame per file, this pass.** The frame is found by a
  fixed name, not a per-document identifier — `payload.json` deliberately
  carries no filename (privacy, same as the IR), so there is nothing to key a
  second frame on. Building a second document into the same file overwrites
  the first's build frame; components on "Components" are unaffected, since
  candidates from unrelated documents don't share ids. Multi-document files
  are future work.

## Verification

- `emitter`: `npm test` (matching inside/outside tolerance in both directions,
  candidate match and no-match, px conversion, profile defaults, the privacy
  scan). `tsc --noEmit` clean.
- `figma-plugin`: `tsc --noEmit` clean; `npm run build` produces `code.js`.
- **Manual, in Figma Desktop** — no way around this, per architecture.md:
  load the rebuilt plugin, build from a payload derived from a synthetic
  corpus, confirm masters appear once on "Components," instances land at the
  right geometry, a second run updates rather than duplicates, and a
  deliberately-broken font name produces a reported skip instead of a crash.

## Risks

- **Matching is a nearest-token lookup against a *serialized* Inventory**, not
  the live clustering state S2 held in memory (`PaletteResult.cluster_of` /
  `TypeScaleResult.cluster_of` never leave Python). It reconstructs "which
  cluster" from the reported tokens and tolerances alone. For a document that
  was part of the original corpus this reproduces the same assignment; for a
  new document of the same template it's a reasonable generalization, but
  unverified against a real corpus, same caveat S2 already carries.
- **The build frame is destroyed and rebuilt on every run.** Any manual tweak
  a person made inside it (a nudge, a color override) is lost on the next
  build. Components on the separate "Components" page survive; nothing inside
  the build frame is safe to hand-edit yet.
- **No headless verification of the plugin half.** Its correctness rests on a
  manual walkthrough, not an automated suite — a real gap, not a hidden one.
