import { IR_VERSION } from "../src/ir.js";
import type { IRDocument, IRNode, Page, ShapeKind, ShapeNode, TextNode } from "../src/ir.js";
import { INVENTORY_VERSION } from "../src/inventory.js";
import type { ColorToken, Inventory, ShapeCandidate, SizeToken, TextCandidate } from "../src/inventory.js";

export function colorToken(hex: string, overrides: Partial<ColorToken> = {}): ColorToken {
  return { hex, count: 1, max_delta: 0, roles: {}, ...overrides };
}

export function sizeToken(overrides: Partial<SizeToken> = {}): SizeToken {
  return { family: "Helvetica", italic: false, size: 12, count: 1, max_delta: 0, ...overrides };
}

export function shapeCandidate(overrides: Partial<ShapeCandidate> = {}): ShapeCandidate {
  return {
    id: "shape-0",
    shape: "rect",
    width: 100,
    height: 50,
    count: 2,
    documents: 1,
    presence_ratio: 1,
    variant: false,
    max_size_delta: 0,
    occurrences: [],
    ...overrides,
  };
}

export function textCandidate(overrides: Partial<TextCandidate> = {}): TextCandidate {
  return {
    id: "text-0",
    family: "Helvetica",
    italic: false,
    size: 12,
    count: 2,
    documents: 1,
    presence_ratio: 1,
    variant: false,
    sample_texts: [],
    occurrences: [],
    ...overrides,
  };
}

export function inventory(overrides: Partial<Inventory> = {}): Inventory {
  return {
    inventory_version: INVENTORY_VERSION,
    corpus: { documents: 1, pages: 1, nodes: 0 },
    tolerances: { color: 6, size: 0.5, spacing: 1, min_occurrences: 2 },
    palette: [],
    type_scale: [],
    spacing: [],
    shape_candidates: [],
    text_candidates: [],
    unclustered_shapes: 0,
    unclustered_text: 0,
    ...overrides,
  };
}

export function rectNode(
  id: string,
  x: number,
  y: number,
  w: number,
  h: number,
  fill?: string,
  overrides: Partial<ShapeNode> = {},
): ShapeNode {
  return shapeNode(id, "rect", x, y, w, h, fill, overrides);
}

export function shapeNode(
  id: string,
  shape: ShapeKind,
  x: number,
  y: number,
  w: number,
  h: number,
  fill?: string,
  overrides: Partial<ShapeNode> = {},
): ShapeNode {
  return {
    id,
    kind: "shape",
    shape,
    bbox: { x, y, w, h },
    z: 0,
    closed: true,
    ...(fill ? { fill: { hex: fill, alpha: 1 } } : {}),
    ...overrides,
  };
}

export function textNode(
  id: string,
  x: number,
  y: number,
  w: number,
  h: number,
  text: string,
  overrides: Partial<TextNode> = {},
): TextNode {
  return {
    id,
    kind: "text",
    text,
    bbox: { x, y, w, h },
    z: 0,
    font: { family: "Helvetica", size: 12, italic: false },
    color: { hex: "#111111", alpha: 1 },
    color_confidence: "exact",
    ...overrides,
  };
}

export function page(nodes: IRNode[], overrides: Partial<Page> = {}): Page {
  return { index: 0, width: 612, height: 792, rotation: 0, nodes, ...overrides };
}

export function irDoc(pages: Page[]): IRDocument {
  return { ir_version: IR_VERSION, source: { page_count: pages.length }, pages };
}
