# S4 — Acceptance checklist

Fixed at planning time. A stage is done when every box is checked against a
real run, not when the code exists. Items that turn out to be wrong get struck
through with a reason — never quietly rewritten to match what was built.

Split in two: `emitter/` is verified by an automated suite; the plugin's build
step has no headless runner and is verified by a manual walkthrough in Figma
Desktop, per architecture.md ("the build step requires Figma Desktop.
Headless is impossible"). Items in that second group stay unchecked until that
walkthrough actually happens.

## Emitter — runs

- [x] `node dist/src/cli.js doc.ir.json corpus.inventory.json -o out.payload.json`
      succeeds without a profile (uses defaults for every candidate)
- [x] Succeeds with a profile that names and componentizes specific candidates
- [x] A document not part of the original corpus still emits a payload —
      matching degrades gracefully to `candidateId: null`, never a crash

## Emitter — matching

- [x] A node whose color is within `tolerances.color` of a `ColorToken`
      resolves to that token's hex; one just outside resolves to none
- [x] A text node whose size is within `tolerances.size` of a `SizeToken` (same
      family/weight/italic) resolves to that token; a different family never
      matches regardless of size
- [x] A node whose resolved signature equals a `ShapeCandidate`/`TextCandidate`
      gets that `candidateId`; one that doesn't gets `null`, never a guessed
      nearest candidate
- [x] Matching is deterministic: same inputs, same payload, twice

## Emitter — payload and profile

- [x] Every bbox in the payload is the IR bbox × 4/3, matching the ratio S3
      measured for Figma's SVG import
- [x] A candidate present in `profile.candidates` gets that entry's `name` /
      `component` / `liveText`; one absent falls back to `profile.defaults`
- [x] `emitter/example.profile.json` is never read unless explicitly passed —
      no default profile is silently applied

## Emitter — privacy and engineering

- [x] No absolute path or source filename anywhere in `payload.json`
- [x] `match.ts` and `payload.ts` contain no `fs`/`path` import — asserted by a
      test, not by convention; only `cli.ts` touches the filesystem
- [x] `tsc --noEmit` clean; `npm test` passes (22/22)
- [x] No dependency beyond `typescript` in `emitter/package.json`
      (`@types/node` is a devDependency for compiling against Node's own
      globals, not a runtime dependency the built CLI carries)

## Plugin — mechanical correctness (manual, Figma Desktop)

Verified 2026-08-11 against two demo payloads: 3 documents' worth of synthetic
IR → `pdf2figma inventory` → `emit --profile` (componentizing the recurring
card and header, plus a deliberately-broken font name to exercise the skip
path), and a second, minimal document adding one `path`-shape and one `image`
node specifically to exercise that skip path. Checked structurally against the live file's
node tree and visually in Figma Desktop.

- [x] Building a payload with one componentized shape candidate creates
      exactly one master on a "Components" page and one instance in the build
      frame, positioned at the payload's bbox — confirmed both structurally
      (exact bbox match) and visually
- [x] Running the same build again does not create a second master — the
      existing one (found via `getPluginData('candidateId')`) is reused —
      confirmed: same node ids before/after a second build, counts reported
      `2 reused` rather than `4 created`
- [x] The build frame's previous contents are cleared before rebuilding; the
      "Components" page is never cleared — same 2 masters survived multiple
      rebuilds; the frame's contents matched the payload exactly each time,
      never accumulating
- [x] A live-text candidate with a loadable font shows the real text content
      on the instance, not the master's placeholder — instance showed
      "Report — Q1", the master's own placeholder is "header"
- [x] A candidate naming a font Figma cannot load is skipped, reported in the
      status line, and does not stop the rest of the build — status read
      "...1 skipped"; the node never appeared in the build frame; every other
      node still built
- [x] A `path`- or `image`-kind one-off is skipped and counted, never rendered
      as a placeholder box — second walkthrough with a document containing one
      `text`, one `path`-shape and one `image` node: status read "1 plain
      node(s), 2 skipped", and the build frame held exactly the text node,
      confirmed via `get_metadata` — no placeholder for either skipped node
- [x] `tsc --noEmit` clean; `npm run build` produces `code.js` — verified by
      compiling; the manifest's `"main": "code.js"` is unchanged
- [x] The manifest.json is unchanged — main resolved to the compiled
      `code.js` in a real Figma Desktop load (the plugin ran at all, which
      requires this)

**Bug found and fixed during this walkthrough**: new component masters had
no explicit position and all landed at `(0, 0)` on the "Components" page,
overlapping. Fixed in `figma-plugin/src/code.ts` (`nextMasterX`) — masters
now lay out left to right with a fixed gap. Re-verified after the fix:
masters separated, idempotency still held (no duplicates from the fix
itself).

## Explicitly not in S4

Listed so their absence is not mistaken for an oversight: Figma Variables,
variants (no variant axis exists until S2 produces composite candidates),
auto layout, per-instance idempotency, image/path reconstruction, multiple
documents built into the same file (one fixed-name build frame per file, this
pass), font repair.
