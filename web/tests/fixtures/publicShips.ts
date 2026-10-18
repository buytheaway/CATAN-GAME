import type { EdgeTuple } from "../../src/components/BoardView.types";
import { publicFogFixture } from "./publicFog";

/** Synthetic PUBLIC scene. Legal lists are fixture inputs, never a frontend rule evaluator. */
export function publicShipFixture(large = false) {
  const state = publicFogFixture(large ? "large" : "partial");
  const water = state.edges!.filter(e => state.edge_adj_hexes![e.join(",")]
    .some(i => state.tiles[i].terrain === "sea"));
  const coast = water.find(e => state.edge_adj_hexes![e.join(",")].some(i => state.tiles[i].terrain === "forest"))!;
  const target = water.find(e => e.join(",") !== coast.join(",") && e.some(v => coast.includes(v))
    && state.edge_adj_hexes![e.join(",")].some(i => state.tiles[i].visibility === "hidden"))
    ?? water.find(e => e.join(",") !== coast.join(",") && e.some(v => coast.includes(v)))!;
  const anchor = coast.find(v => target.includes(v))!;
  state.occupied_v = { [anchor]: [0, 1] };
  delete state.occupied_e[coast.join(",")]; delete state.occupied_e[target.join(",")];
  state.occupied_ships = large ? Object.fromEntries(water.filter(e => e.join(",") !== target.join(","))
    .slice(0, 24).map((e, i) => [e.join(","), i % 2])) : { [coast.join(",")]: 0 };
  state.pirate_tile = null;
  state.legal = { pid: 0, settlements: [], roads: [], cities: [], ships: [target],
    robber_tiles: [], pirate_tiles: [], move_ship: { sources: [coast], targets: { [coast.join(",")]: [target] } } };
  state.map_meta = { name: "Synthetic public ship animation preview" };
  return state;
}

export function shipPreviewChange(state: ReturnType<typeof publicShipFixture>, move: boolean) {
  const source = state.legal?.move_ship?.sources[0], target = state.legal?.ships?.[0] as EdgeTuple | undefined;
  if (!source || !target || state.occupied_ships[target.join(",")] != null) return null;
  if (move) delete state.occupied_ships[source.join(",")];
  state.occupied_ships[target.join(",")] = 0;
  state.legal = { pid: 0, settlements: [], roads: [], ships: [], cities: [], robber_tiles: [], pirate_tiles: [] };
  return { source, target };
}
