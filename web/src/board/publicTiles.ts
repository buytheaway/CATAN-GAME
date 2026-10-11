import type { EdgeTuple, GameState, Tile } from "../components/BoardView.types";
import { edgeId } from "./constants";

export type KnownTerrain = "forest" | "hills" | "pasture" | "fields" | "mountains" | "desert" | "sea" | "gold";
export type TileVisibility = "hidden" | "revealed";
export interface PublicTileVisual {
  visibility: TileVisibility;
  terrain: KnownTerrain | "fog";
  number: number | null;
}

const TERRAINS = new Set<string>(["forest", "hills", "pasture", "fields", "mountains", "desert", "sea", "gold"]);
const ALIASES: Record<string, KnownTerrain> = { wood: "forest", clay: "hills", brick: "hills",
  sheep: "pasture", wheat: "fields", ore: "mountains" };

/** Fail closed for unknown/malformed public tiles. Never retain hidden content in a render model. */
export function publicTileVisual(tile: Partial<Tile> | null | undefined): PublicTileVisual {
  const terrain = typeof tile?.terrain === "string" ? tile.terrain : "";
  const known = TERRAINS.has(terrain) ? terrain as KnownTerrain
    : typeof ALIASES[terrain] === "string" ? ALIASES[terrain] : undefined;
  if (!known || tile?.visibility !== undefined && tile.visibility !== "revealed")
    return { visibility: "hidden", terrain: "fog", number: null };
  const number = tile?.number;
  return { visibility: "revealed", terrain: known,
    number: Number.isInteger(number) && number! >= 2 && number! <= 12 && number !== 7 ? number! : null };
}

export const isHiddenTile = (tile: Partial<Tile> | null | undefined) => publicTileVisual(tile).visibility === "hidden";
export const isKnownLand = (tile: Partial<Tile> | null | undefined) => {
  const visual = publicTileVisual(tile);
  return visual.visibility === "revealed" && visual.terrain !== "sea";
};
export const isKnownSea = (tile: Partial<Tile> | null | undefined) => publicTileVisual(tile).terrain === "sea";

/** Geometry is public, independent of visibility. Axial fallback matches the server's pointy hexes. */
export function publicTileCenter(tile: Partial<Tile> | null | undefined, size: number): [number, number] {
  if (Array.isArray(tile?.center) && tile.center.length === 2 && tile.center.every(Number.isFinite))
    return [tile.center[0], tile.center[1]];
  const q = Number.isFinite(tile?.q) ? tile!.q! : 0;
  const r = Number.isFinite(tile?.r) ? tile!.r! : 0;
  const scale = Number.isFinite(size) && size > 0 ? size : 58;
  return [scale * Math.sqrt(3) * (q + r / 2), scale * 1.5 * r];
}

/** A port beside unknown terrain must not add a coastline hint. Historical non-Fog ports still work. */
export function isPublicPort(state: Pick<GameState, "tiles" | "edge_adj_hexes">, edge: EdgeTuple): boolean {
  const adjacent = state.edge_adj_hexes?.[edgeId(edge)];
  if (!adjacent?.length) return !state.tiles.some(isHiddenTile);
  return adjacent.every(i => Number.isInteger(i) && !isHiddenTile(state.tiles[i]));
}
