/**
 * `buildPayload` is the one place matching and profile decisions turn into
 * something the plugin can act on mechanically. Everything painted uses the
 * node's own *raw* value (exact color, exact size, exact text) — resolution
 * against Inventory tokens is used only to decide *identity* (which
 * candidate, if any), never what gets painted. Rounding a genuinely unique
 * one-off to its nearest palette entry would lose fidelity for no reason;
 * see `docs/specs/s4-emit-build/spec.md`.
 */

import { isShapeNode, isTextNode } from "./ir.js";
import type { IRDocument, IRNode, ShapeNode, TextNode } from "./ir.js";
import type { Inventory } from "./inventory.js";
import { matchShapeCandidate, matchTextCandidate, nearestColorToken, nearestSizeToken } from "./match.js";
import { resolveProfileEntry } from "./profile.js";
import type { Profile } from "./profile.js";

export const PAYLOAD_VERSION = "0.1";

/**
 * Figma imports SVG as CSS pixels, where one point is 4/3px at 96dpi —
 * measured in S3 (`figma-plugin/README.md`), not assumed. The pt->px
 * conversion happens exactly once, here — for every length the plugin paints
 * with: bbox, font size and stroke width alike. Font size and stroke width were
 * once left in points while bboxes were converted, so every built text ran at
 * 75% of its source size; a symmetric omission in the plugin's export hid it
 * from structural verify (see the regression test in `test/payload.test.ts`).
 */
export const PT_TO_PX = 4 / 3;

export interface PayloadBBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type PayloadNodeKind = "rect" | "ellipse" | "line" | "text" | "unsupported";

export interface PayloadNode {
  id: string;
  kind: PayloadNodeKind;
  candidateId: string | null;
  component: boolean;
  liveText: boolean;
  name: string;
  bbox: PayloadBBox;
  fill?: string;
  strokeColor?: string;
  strokeWidth?: number;
  font?: { family: string; size: number; weight?: number; italic: boolean };
  text?: string;
  unsupportedReason?: string;
}

export interface Payload {
  payload_version: string;
  page: { width: number; height: number };
  nodes: PayloadNode[];
}

export function buildPayload(
  ir: IRDocument,
  pageIndex: number,
  inventory: Inventory,
  profile?: Profile,
): Payload {
  const page = ir.pages[pageIndex];
  if (page === undefined) {
    throw new RangeError(`page ${pageIndex} does not exist (document has ${ir.pages.length})`);
  }

  const nodes = page.nodes.map((node: IRNode): PayloadNode => {
    if (isShapeNode(node)) return shapeToPayload(node, inventory, profile);
    if (isTextNode(node)) return textToPayload(node, inventory, profile);
    // The only remaining IRNode variant is ImageNode: no bytes survive S1's
    // extraction, so there is nothing to build regardless of matching.
    return unsupportedPayload(node.id, "image-bytes-unavailable");
  });

  return {
    payload_version: PAYLOAD_VERSION,
    page: { width: page.width * PT_TO_PX, height: page.height * PT_TO_PX },
    nodes,
  };
}

function scaleBBox(bbox: { x: number; y: number; w: number; h: number }): PayloadBBox {
  return {
    x: bbox.x * PT_TO_PX,
    y: bbox.y * PT_TO_PX,
    w: bbox.w * PT_TO_PX,
    h: bbox.h * PT_TO_PX,
  };
}

function unsupportedPayload(id: string, reason: string): PayloadNode {
  return {
    id,
    kind: "unsupported",
    candidateId: null,
    component: false,
    liveText: false,
    name: id,
    bbox: { x: 0, y: 0, w: 0, h: 0 },
    unsupportedReason: reason,
  };
}

function shapeToPayload(node: ShapeNode, inventory: Inventory, profile: Profile | undefined): PayloadNode {
  if (node.shape === "path") {
    // No raw contour survives S1's classification (bbox only) — nothing to
    // build, matched candidate or not. See spec's "Image and path
    // reconstruction" non-goal.
    return unsupportedPayload(node.id, "path-geometry-unavailable");
  }

  const resolvedFill = node.fill
    ? nearestColorToken(node.fill.hex, inventory.palette, inventory.tolerances.color)
    : null;
  const resolvedStroke = node.stroke
    ? nearestColorToken(node.stroke.color.hex, inventory.palette, inventory.tolerances.color)
    : null;

  const candidate = matchShapeCandidate(
    node.shape,
    node.bbox.w,
    node.bbox.h,
    {
      fillHex: resolvedFill?.hex,
      strokeHex: resolvedStroke?.hex,
      strokeWidth: node.stroke?.width,
    },
    inventory.shape_candidates,
    inventory.tolerances.size,
  );

  const candidateId = candidate?.id ?? null;
  const entry = resolveProfileEntry(profile, candidateId);
  const name = entry.name ?? candidateId ?? node.id;

  return {
    id: node.id,
    kind: node.shape,
    candidateId,
    component: candidateId !== null && (entry.component ?? false),
    liveText: false,
    name,
    bbox: scaleBBox(node.bbox),
    fill: node.fill?.hex,
    strokeColor: node.stroke?.color.hex,
    strokeWidth: node.stroke ? node.stroke.width * PT_TO_PX : undefined,
  };
}

function textToPayload(node: TextNode, inventory: Inventory, profile: Profile | undefined): PayloadNode {
  const resolvedColor = node.color
    ? nearestColorToken(node.color.hex, inventory.palette, inventory.tolerances.color)
    : null;
  const resolvedSize = nearestSizeToken(
    node.font.size,
    node.font.family,
    node.font.weight,
    node.font.italic,
    inventory.type_scale,
    inventory.tolerances.size,
  );

  const candidate = matchTextCandidate(
    node.font.family,
    node.font.weight,
    node.font.italic,
    resolvedSize?.size,
    resolvedColor?.hex,
    inventory.text_candidates,
  );

  const candidateId = candidate?.id ?? null;
  const entry = resolveProfileEntry(profile, candidateId);
  const name = entry.name ?? candidateId ?? node.id;

  return {
    id: node.id,
    kind: "text",
    candidateId,
    component: candidateId !== null && (entry.component ?? false),
    liveText: entry.liveText ?? false,
    name,
    bbox: scaleBBox(node.bbox),
    fill: node.color?.hex,
    font: {
      family: node.font.family,
      size: node.font.size * PT_TO_PX,
      weight: node.font.weight,
      italic: node.font.italic,
    },
    text: node.text,
  };
}
