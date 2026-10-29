import assert from "node:assert/strict";
import test from "node:test";

import type { ShapeNode } from "../src/ir.js";
import { buildPayload, PT_TO_PX } from "../src/payload.js";
import {
  colorToken,
  inventory,
  irDoc,
  page,
  rectNode,
  shapeCandidate,
  shapeNode,
  textCandidate,
  textNode,
} from "./fixtures.js";

void test("bbox and page dimensions scale by 4/3, matching S3's measured ratio", () => {
  const doc = irDoc([page([rectNode("r1", 100, 600, 200, 50, "#3355ff")], { width: 612, height: 792 })]);
  const payload = buildPayload(doc, 0, inventory());

  assert.equal(payload.page.width, 612 * PT_TO_PX);
  assert.equal(payload.page.height, 792 * PT_TO_PX);
  const node = payload.nodes[0];
  assert.equal(node?.bbox.x, 100 * PT_TO_PX);
  assert.equal(node?.bbox.w, 200 * PT_TO_PX);
});

void test("a matched candidate is not componentized without a profile", () => {
  const doc = irDoc([page([rectNode("r1", 0, 0, 100, 50, "#3355ff")])]);
  const inv = inventory({
    palette: [colorToken("#3355ff")],
    shape_candidates: [shapeCandidate({ fill: "#3355ff" })],
  });

  const payload = buildPayload(doc, 0, inv);
  assert.equal(payload.nodes[0]?.candidateId, "shape-0");
  assert.equal(payload.nodes[0]?.component, false);
});

void test("a profile entry componentizes and names a matched candidate", () => {
  const doc = irDoc([page([rectNode("r1", 0, 0, 100, 50, "#3355ff")])]);
  const inv = inventory({
    palette: [colorToken("#3355ff")],
    shape_candidates: [shapeCandidate({ fill: "#3355ff" })],
  });
  const profile = { candidates: { "shape-0": { name: "card", component: true } } };

  const payload = buildPayload(doc, 0, inv, profile);
  assert.equal(payload.nodes[0]?.component, true);
  assert.equal(payload.nodes[0]?.name, "card");
});

void test("a one-off node is never componentized even if defaults say so", () => {
  const doc = irDoc([page([rectNode("r1", 0, 0, 100, 50, "#123456")])]);
  const inv = inventory(); // no candidates at all -> this node cannot match
  const profile = { defaults: { component: true } };

  const payload = buildPayload(doc, 0, inv, profile);
  assert.equal(payload.nodes[0]?.candidateId, null);
  assert.equal(payload.nodes[0]?.component, false);
  assert.equal(payload.nodes[0]?.name, "r1");
});

void test("path-kind shapes are unsupported regardless of matching", () => {
  const node: ShapeNode = shapeNode("p1", "path", 0, 0, 10, 10);
  const doc = irDoc([page([node])]);

  const payload = buildPayload(doc, 0, inventory());
  assert.equal(payload.nodes[0]?.kind, "unsupported");
  assert.equal(payload.nodes[0]?.unsupportedReason, "path-geometry-unavailable");
});

void test("image nodes are unsupported — no bytes survive extraction", () => {
  const doc = irDoc([
    page([{ id: "i1", kind: "image", image_id: "img-0", bbox: { x: 0, y: 0, w: 10, h: 10 }, z: 0 }]),
  ]);

  const payload = buildPayload(doc, 0, inventory());
  assert.equal(payload.nodes[0]?.kind, "unsupported");
  assert.equal(payload.nodes[0]?.unsupportedReason, "image-bytes-unavailable");
});

void test("liveText comes from the profile, independent of componentization", () => {
  const doc = irDoc([page([textNode("t1", 0, 0, 100, 20, "Hello")])]);
  const inv = inventory({ text_candidates: [textCandidate({ size: 12, color: "#111111" })] });
  const profile = { defaults: { liveText: true } };

  const payload = buildPayload(doc, 0, inv, profile);
  assert.equal(payload.nodes[0]?.liveText, true);
  assert.equal(payload.nodes[0]?.component, false); // defaults.component still false
  assert.equal(payload.nodes[0]?.text, "Hello");
});

void test("an out-of-range page throws rather than silently building an empty one", () => {
  const doc = irDoc([page([])]);
  assert.throws(() => buildPayload(doc, 5, inventory()), RangeError);
});

void test("font size and stroke width are converted pt->px like the bbox", () => {
  // Regression guard: both were once passed through in points while the bbox
  // was converted, so every built text ran at 75% of its source size. The
  // plugin's export left them unconverted too, which kept structural verify
  // blind to it; the demo build's side-by-side render is what showed it.
  const doc = irDoc([
    page([
      textNode("t1", 0, 0, 100, 20, "Hello", { font: { family: "Helvetica", size: 12, italic: false } }),
      rectNode("r1", 0, 30, 100, 10, "#ffffff", { stroke: { color: { hex: "#000000", alpha: 1 }, width: 0.75 } }),
    ]),
  ]);

  const payload = buildPayload(doc, 0, inventory());
  assert.equal(payload.nodes[0]?.font?.size, 12 * PT_TO_PX);
  assert.equal(payload.nodes[1]?.strokeWidth, 0.75 * PT_TO_PX);
});

void test("font.family passes through unmodified — payload.ts never re-derives it", () => {
  // Regression guard for the other half of the font-suffix fix
  // (`_font_of` in `extract/pdf.py`): whatever clean family name extraction
  // hands over, buildPayload must carry through byte-for-byte. A "clever"
  // future change here that tries to normalize/re-derive family names would
  // silently reintroduce the same class of figma.loadFontAsync failure.
  const doc = irDoc([
    page([textNode("t1", 0, 0, 100, 20, "Hello", { font: { family: "Helvetica", size: 12, italic: false } })]),
  ]);

  const payload = buildPayload(doc, 0, inventory());
  assert.equal(payload.nodes[0]?.font?.family, "Helvetica");
});
