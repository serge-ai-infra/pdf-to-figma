import assert from "node:assert/strict";
import test from "node:test";

import { matchShapeCandidate, matchTextCandidate, nearestColorToken, nearestSizeToken } from "../src/match.js";
import { colorToken, shapeCandidate, sizeToken, textCandidate } from "./fixtures.js";

void test("nearestColorToken merges within tolerance", () => {
  const palette = [colorToken("#000000")];
  const match = nearestColorToken("#000005", palette, 6);
  assert.equal(match?.hex, "#000000");
});

void test("nearestColorToken returns null beyond tolerance", () => {
  const palette = [colorToken("#000000")];
  assert.equal(nearestColorToken("#0000ff", palette, 6), null);
});

void test("nearestColorToken picks the closer of two candidates", () => {
  const palette = [colorToken("#000000"), colorToken("#101010")];
  const match = nearestColorToken("#0a0a0a", palette, 20);
  assert.equal(match?.hex, "#101010");
});

void test("nearestSizeToken requires an exact family/weight/italic match", () => {
  const scale = [sizeToken({ family: "Times", size: 12 })];
  assert.equal(nearestSizeToken(12, "Helvetica", undefined, false, scale, 5), null);
});

void test("nearestSizeToken merges within tolerance, rejects beyond it", () => {
  const scale = [sizeToken({ size: 12 })];
  assert.equal(nearestSizeToken(12.3, "Helvetica", undefined, false, scale, 0.5)?.size, 12);
  assert.equal(nearestSizeToken(20, "Helvetica", undefined, false, scale, 0.5), null);
});

void test("matchShapeCandidate matches on kind, resolved style and geometry", () => {
  const candidates = [shapeCandidate({ fill: "#3355ff" })];
  const match = matchShapeCandidate("rect", 100, 50, { fillHex: "#3355ff" }, candidates, 1);
  assert.equal(match?.id, "shape-0");
});

void test("matchShapeCandidate rejects a different shape kind", () => {
  const candidates = [shapeCandidate({ shape: "rect", fill: "#3355ff" })];
  const match = matchShapeCandidate("ellipse", 100, 50, { fillHex: "#3355ff" }, candidates, 1);
  assert.equal(match, null);
});

void test("matchShapeCandidate rejects geometry further than the size tolerance", () => {
  const candidates = [shapeCandidate({ fill: "#3355ff", width: 100, height: 50 })];
  const match = matchShapeCandidate("rect", 100, 90, { fillHex: "#3355ff" }, candidates, 1);
  assert.equal(match, null);
});

void test("matchShapeCandidate treats undefined fill/stroke as its own case", () => {
  const candidates = [shapeCandidate({ fill: undefined })];
  const withFill = matchShapeCandidate("rect", 100, 50, { fillHex: "#3355ff" }, candidates, 1);
  const withoutFill = matchShapeCandidate("rect", 100, 50, {}, candidates, 1);
  assert.equal(withFill, null);
  assert.equal(withoutFill?.id, "shape-0");
});

void test("matchTextCandidate returns null when no size token resolved", () => {
  const candidates = [textCandidate()];
  const match = matchTextCandidate("Helvetica", undefined, false, undefined, undefined, candidates);
  assert.equal(match, null);
});

void test("matchTextCandidate matches on exact resolved size and color", () => {
  const candidates = [textCandidate({ size: 12, color: "#111111" })];
  const match = matchTextCandidate("Helvetica", undefined, false, 12, "#111111", candidates);
  assert.equal(match?.id, "text-0");
});

void test("matchTextCandidate rejects a different family even at the same size", () => {
  const candidates = [textCandidate({ family: "Times", size: 12 })];
  const match = matchTextCandidate("Helvetica", undefined, false, 12, undefined, candidates);
  assert.equal(match, null);
});
