/**
 * Types mirroring `src/pdf2figma/ir/model.py`'s JSON shape.
 *
 * Pydantic's `model_dump(mode="json", exclude_none=True)` drops any field
 * whose value is `None` entirely, rather than emitting `null` — so an
 * optional field here is `?:`, never `| null`. A field with a non-None
 * default (`italic`, `alpha`, `closed`, `rotation`) is always present.
 */

export const IR_VERSION = "0.1";

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Color {
  hex: string;
  alpha: number;
}

export interface Stroke {
  color: Color;
  width: number;
}

export interface Font {
  family: string;
  size: number;
  weight?: number;
  italic: boolean;
}

export type Confidence = "exact" | "approx" | "unknown";

export type ShapeKind = "rect" | "ellipse" | "line" | "path";

interface NodeBase {
  id: string;
  bbox: BBox;
  z: number;
}

export interface TextNode extends NodeBase {
  kind: "text";
  text: string;
  font: Font;
  color?: Color;
  color_confidence: Confidence;
}

export interface ShapeNode extends NodeBase {
  kind: "shape";
  shape: ShapeKind;
  fill?: Color;
  stroke?: Stroke;
  closed: boolean;
}

export interface ImageNode extends NodeBase {
  kind: "image";
  image_id: string;
  mime?: string;
}

export type IRNode = TextNode | ShapeNode | ImageNode;

export interface Page {
  index: number;
  width: number;
  height: number;
  rotation: number;
  nodes: IRNode[];
}

export interface SourceInfo {
  page_count: number;
  producer?: string;
  creator?: string;
  title?: string;
  color_space?: string;
}

export interface IRDocument {
  ir_version: string;
  source: SourceInfo;
  pages: Page[];
}

export function isTextNode(node: IRNode): node is TextNode {
  return node.kind === "text";
}

export function isShapeNode(node: IRNode): node is ShapeNode {
  return node.kind === "shape";
}

export function isImageNode(node: IRNode): node is ImageNode {
  return node.kind === "image";
}
