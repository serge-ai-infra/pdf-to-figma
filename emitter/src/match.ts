/**
 * Pure matching: no Figma API, no filesystem — see the note in
 * `docs/specs/s4-emit-build/spec.md` about why that boundary matters here.
 *
 * Every lookup reuses Inventory's own tolerances rather than re-deriving
 * anything. Color and size resolve to a token's own representative value
 * first (nearest within tolerance); candidate matching then compares those
 * *resolved* values by exact equality — a `ShapeCandidate`'s `fill` is
 * already `palette.tokens[cluster].hex`, not a raw instance's color, so
 * fuzzy matching there would be comparing the wrong thing. Only geometry
 * (width/height, which is a candidate's *centroid*, not any single
 * instance's raw value) stays fuzzy.
 */

import type { ShapeKind } from "./ir.js";
import type { ColorToken, ShapeCandidate, SizeToken, TextCandidate } from "./inventory.js";

function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

function colorDistance(a: string, b: string): number {
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  return Math.sqrt((ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2);
}

export function nearestColorToken(
  hex: string,
  palette: readonly ColorToken[],
  tolerance: number,
): ColorToken | null {
  let best: ColorToken | null = null;
  let bestDistance = Infinity;

  for (const token of palette) {
    const distance = colorDistance(hex, token.hex);
    if (distance <= tolerance && distance < bestDistance) {
      best = token;
      bestDistance = distance;
    }
  }

  return best;
}

export function nearestSizeToken(
  size: number,
  family: string,
  weight: number | undefined,
  italic: boolean,
  typeScale: readonly SizeToken[],
  tolerance: number,
): SizeToken | null {
  let best: SizeToken | null = null;
  let bestDistance = Infinity;

  for (const token of typeScale) {
    if (token.family !== family || token.weight !== weight || token.italic !== italic) {
      continue;
    }
    const distance = Math.abs(size - token.size);
    if (distance <= tolerance && distance < bestDistance) {
      best = token;
      bestDistance = distance;
    }
  }

  return best;
}

export interface ResolvedShapeStyle {
  fillHex?: string;
  strokeHex?: string;
  strokeWidth?: number;
}

/**
 * `fillHex`/`strokeHex` must already be resolved token hexes (or `undefined`
 * for "no fill"/"no stroke"), not a raw node's color — see the module note.
 */
export function matchShapeCandidate(
  shape: ShapeKind,
  width: number,
  height: number,
  style: ResolvedShapeStyle,
  candidates: readonly ShapeCandidate[],
  sizeTolerance: number,
): ShapeCandidate | null {
  let best: ShapeCandidate | null = null;
  let bestDistance = Infinity;

  for (const candidate of candidates) {
    if (candidate.shape !== shape) continue;
    if ((candidate.fill ?? null) !== (style.fillHex ?? null)) continue;
    if ((candidate.stroke_color ?? null) !== (style.strokeHex ?? null)) continue;
    if (!strokeWidthMatches(candidate.stroke_width, style.strokeWidth, sizeTolerance)) continue;

    const distance = Math.hypot(width - candidate.width, height - candidate.height);
    if (distance <= sizeTolerance && distance < bestDistance) {
      best = candidate;
      bestDistance = distance;
    }
  }

  return best;
}

function strokeWidthMatches(
  candidateWidth: number | undefined,
  nodeWidth: number | undefined,
  tolerance: number,
): boolean {
  if (candidateWidth === undefined && nodeWidth === undefined) return true;
  if (candidateWidth === undefined || nodeWidth === undefined) return false;
  return Math.abs(candidateWidth - nodeWidth) <= tolerance;
}

/**
 * `resolvedSize` must already be a matched `SizeToken`'s own `size` (or
 * `undefined` if none matched) — a `TextCandidate`'s `size` is exactly that
 * token value, so this compares by exact equality, not tolerance.
 */
export function matchTextCandidate(
  family: string,
  weight: number | undefined,
  italic: boolean,
  resolvedSize: number | undefined,
  resolvedColorHex: string | undefined,
  candidates: readonly TextCandidate[],
): TextCandidate | null {
  if (resolvedSize === undefined) return null;

  for (const candidate of candidates) {
    if (candidate.family !== family) continue;
    if (candidate.weight !== weight) continue;
    if (candidate.italic !== italic) continue;
    if (candidate.size !== resolvedSize) continue;
    if ((candidate.color ?? null) !== (resolvedColorHex ?? null)) continue;
    return candidate;
  }

  return null;
}
