import type { GameSnapshot } from "../../src/game/presentation";
import { publicShipFixture } from "./publicShips";

export type BuildingPreviewKind = "road" | "settlement" | "upgrade";

/** Synthetic PUBLIC display frames, not an engine, private recipe or legality evaluator. */
export function publicBuildingFixture(large = false) {
  const state = publicShipFixture(large);
  const landEdges = state.edges!.filter(e => state.edge_adj_hexes![e.join(",")].includes(0));
  const free = landEdges.filter(e => !Object.hasOwn(state.occupied_e, e.join(","))
    && !Object.hasOwn(state.occupied_ships, e.join(",")));
  const roads = [...free].sort((a, b) => Number(state.edge_adj_hexes![b.join(",")]
    .some(i => state.tiles[i].visibility === "hidden")) - Number(state.edge_adj_hexes![a.join(",")]
    .some(i => state.tiles[i].visibility === "hidden"))).slice(0, 2);
  const settlement = roads.flat().find(v => !Object.hasOwn(state.occupied_v, v))!;
  const home = Number(Object.keys(state.occupied_v)[0]);
  const city = state.edges!.filter(e => state.edge_adj_hexes![e.join(",")].includes(2)).flat()
    .find(v => v !== home && v !== settlement && !roads.flat().includes(v))!;
  state.occupied_v[city] = [1, 2];
  state.legal = { ...state.legal!, roads, settlements: [settlement], cities: [home] };
  state.map_meta = { name: "Synthetic public construction preview" };
  return state;
}

/** A new public display frame is published by the harness, never a live command. */
export function buildingPreviewChange(state: GameSnapshot, kind: BuildingPreviewKind) {
  const legal = state.legal!;
  if (kind === "road") {
    const edge = legal.roads.find(e => !Object.hasOwn(state.occupied_e, e.join(",")));
    if (!edge) return false;
    state.occupied_e[edge.join(",")] = 0;
    legal.roads = legal.roads.filter(e => e.join(",") !== edge.join(","));
    for (const i of state.edge_adj_hexes![edge.join(",")]) if (state.tiles[i].visibility === "hidden")
      state.tiles[i] = { ...state.tiles[i], visibility: "revealed", terrain: "forest", number: 11 };
  } else if (kind === "settlement") {
    const id = legal.settlements.find(v => !Object.hasOwn(state.occupied_v, v));
    if (id == null) return false;
    state.occupied_v[id] = [0, 1];
    legal.settlements = legal.settlements.filter(v => v !== id);
    legal.cities = [...legal.cities, id];
  } else {
    const id = [...legal.cities].reverse().find(v => state.occupied_v[v]?.[0] === 0 && state.occupied_v[v]?.[1] === 1);
    if (id == null) return false;
    state.occupied_v[id] = [0, 2];
    legal.cities = legal.cities.filter(v => v !== id);
  }
  return true;
}
