/**
 * Types mirroring `src/pdf2figma/inventory/model.py`'s JSON shape.
 * Same `exclude_none` convention as `ir.ts` — optional fields, never `| null`.
 */

import type { ShapeKind } from "./ir.js";

export const INVENTORY_VERSION = "0.1";

export interface Tolerances {
  color: number;
  size: number;
  spacing: number;
  min_occurrences: number;
}

export interface CorpusStats {
  documents: number;
  pages: number;
  nodes: number;
}

export interface Occurrence {
  document: number;
  page: number;
  node_id: string;
}

export type Role = "fill" | "stroke" | "text";

export interface ColorToken {
  hex: string;
  count: number;
  max_delta: number;
  roles: Partial<Record<Role, number>>;
}

export interface SizeToken {
  family: string;
  weight?: number;
  italic: boolean;
  size: number;
  count: number;
  max_delta: number;
}

export interface SpacingToken {
  axis: "x" | "y";
  gap: number;
  count: number;
  max_delta: number;
}

export interface ShapeCandidate {
  id: string;
  shape: ShapeKind;
  fill?: string;
  stroke_color?: string;
  stroke_width?: number;
  width: number;
  height: number;
  count: number;
  documents: number;
  presence_ratio: number;
  variant: boolean;
  max_size_delta: number;
  occurrences: Occurrence[];
}

export interface TextCandidate {
  id: string;
  family: string;
  weight?: number;
  italic: boolean;
  size: number;
  color?: string;
  count: number;
  documents: number;
  presence_ratio: number;
  variant: boolean;
  sample_texts: string[];
  occurrences: Occurrence[];
}

export interface Inventory {
  inventory_version: string;
  corpus: CorpusStats;
  tolerances: Tolerances;
  palette: ColorToken[];
  type_scale: SizeToken[];
  spacing: SpacingToken[];
  shape_candidates: ShapeCandidate[];
  text_candidates: TextCandidate[];
  unclustered_shapes: number;
  unclustered_text: number;
}
