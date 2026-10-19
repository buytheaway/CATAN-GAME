import { publicShipFixture } from "./publicShips";

/** Public synthetic art comparison only; no game recipe or legality evaluator. */
export function publicShipArtFixture(large = false) {
  const state = publicShipFixture(large);
  state.players.push(
    { pid: 2, name: "Verdant", color: "green", vp: 2, resource_count: 3, dev_count: 0 },
    { pid: 3, name: "Amber", color: "orange", vp: 2, resource_count: 3, dev_count: 0 },
  );
  const target = state.legal!.ships![0].join(",");
  const water = state.edges!.filter(edge => edge.join(",") !== target
    && state.edge_adj_hexes![edge.join(",")].some(index => state.tiles[index].terrain === "sea"));
  // Every edge and owner ID is from the public fixture. The first ship remains
  // the existing source so the established build/move preview callbacks work.
  const source = state.legal!.move_ship!.sources[0].join(",");
  const fleet = [water.find(edge => edge.join(",") === source)!,
    ...water.filter(edge => edge.join(",") !== source)].slice(0, large ? 24 : 4);
  state.occupied_ships = Object.fromEntries(fleet.map((edge, index) => [edge.join(","), index % 4]));
  const city = state.edges!.find(edge => state.edge_adj_hexes![edge.join(",")].includes(2)
    && edge.every(vertex => state.occupied_v[vertex] == null))!;
  state.occupied_v[city[0]] = [1, 2];
  state.map_meta = { name: "Synthetic public ship art comparison" };
  return state;
}
