/**
 * Mirrors `tests/test_privacy.py`'s structural approach: the guarantee is
 * asserted, not reviewed. `cli.ts` is the only file allowed to touch the
 * filesystem — everything downstream of it takes parsed objects, never a
 * path, so there is nowhere for one to leak from even if someone tried.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { buildPayload } from "../src/payload.js";
import { inventory, irDoc, page, rectNode, shapeCandidate } from "./fixtures.js";

const PATH_PATTERN = /\/Users\/|\/home\/|[A-Za-z]:\\\\|\.ir\.json\b/i;
const IO_MARKER = /(?<![\w.])(from ["']node:fs["']|from ["']node:path["'])/;

// Read from the repo source, not the compiled output this test itself runs
// from — `import.meta.url` here is `dist/test/privacy.test.js`.
function sourceOf(relativePath: string): string {
  const url = new URL(`../../${relativePath}`, import.meta.url);
  return readFileSync(fileURLToPath(url), "utf8");
}

void test("match.ts and payload.ts never import fs or path", () => {
  for (const file of ["src/match.ts", "src/payload.ts"]) {
    const source = sourceOf(file);
    assert.equal(IO_MARKER.test(source), false, `${file} should not touch the filesystem`);
  }
});

void test("a built payload contains no filesystem path", () => {
  const doc = irDoc([page([rectNode("r1", 0, 0, 100, 50, "#3355ff")])]);
  const inv = inventory({ shape_candidates: [shapeCandidate({ fill: "#3355ff" })] });

  const payload = buildPayload(doc, 0, inv, { candidates: { "shape-0": { component: true } } });
  assert.equal(PATH_PATTERN.test(JSON.stringify(payload)), false);
});
