/**
 * Utility functions for BoardView component
 */

import type { EdgeTuple, GameState, VertexCoordinates, OccupiedEdge } from "./BoardView.types";
import {
  SQRT3,
  SIZE_RATIOS,
  PLAYER_COLORS,
  STROKE_DASHARRAY,
  STROKE_WIDTH,
} from "./BoardView.constants";

export function hexCorners(cx: number, cy: number, size: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 180) * (60 * i - 30);
    const x = cx + size * Math.cos(angle);
    const y = cy + size * Math.sin(angle);
    pts.push(`${x},${y}`);
  }
  return pts.join(" ");
}

export function edgeKey(a: number, b: number): string {
  return a < b ? `${a},${b}` : `${b},${a}`;
}

export function isEdgesEqual(edge1: EdgeTuple, edge2: EdgeTuple): boolean {
  return edgeKey(edge1[0], edge1[1]) === edgeKey(edge2[0], edge2[1]);
}

export function getVertexCoordinate(
  vertices: VertexCoordinates,
  vid: number
): [number, number] | null {
  const coord = vertices[String(vid)];
  return coord || null;
}

export function isOccupied(occupiedE: OccupiedEdge, a: number, b: number): boolean {
  return occupiedE[edgeKey(a, b)] !== undefined;
}

export function getOccupiedColor(occupiedE: OccupiedEdge, a: number, b: number): string | undefined {
  const owner = occupiedE[edgeKey(a, b)];
  return owner !== undefined ? PLAYER_COLORS[owner] : undefined;
}

export function calculateBounds(
  tiles: any[],
  size: number
): { minX: number; minY: number; width: number; height: number } {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;

  tiles.forEach((t: any) => {
    const [cx, cy] = t.center || [0, 0];
    minX = Math.min(minX, cx - size);
    maxX = Math.max(maxX, cx + size);
    minY = Math.min(minY, cy - size);
    maxY = Math.max(maxY, cy + size);
  });

  const margin = size * SIZE_RATIOS.bounds;
  return {
    minX: minX - margin,
    minY: minY - margin,
    width: maxX - minX + margin * 2,
    height: maxY - minY + margin * 2,
  };
}

export function validVertex(
  vertices: VertexCoordinates,
  vid: string
): boolean {
  return Boolean(vertices[vid]);
}

export function getEdgeAdjacentTiles(
  edgeAdj: Record<string, number[]>,
  key: string
): number[] {
  return edgeAdj[key] || [];
}

export function portRatioLabel(kind: string): string {
  return String(kind).includes("3:1") ? "3:1" : "2:1";
}

/**
 * Normalize action type for comparison
 */
export function normalizeActionType(action: string | null): string | null {
  return action ? String(action).toLowerCase().trim() : null;
}

/**
 * Get human-readable action label
 */
export const ACTION_LABELS: Record<string, string> = {
  settlement: "Settlement",
  road: "Road",
  city: "City",
  ship: "Ship",
  move_ship: "Move Ship",
  pirate: "Pirate",
} as const;

export function getActionLabel(action: string): string {
  return ACTION_LABELS[action] || action;
}
