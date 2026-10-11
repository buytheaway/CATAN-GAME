import type { EdgeTuple, Tile } from "../../src/components/BoardView.types";
import type { GameSnapshot } from "../../src/game/presentation";

/** Synthetic CLIENT-VISIBLE data only. No assignment, recipe, pool, seed or private ledger. */
export function publicFogFixture(mode: "partial" | "hidden" | "large" | "normal" = "partial"): GameSnapshot {
  const size = 58;
  const cells: [number, number][] = mode === "large"
    ? Array.from({ length: 50 }, (_, i) => [i % 10 - 5, Math.floor(i / 10) - 2])
    : [[0, 0], [1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];
  const examples: Array<[string, number | null]> = [["forest", 5], ["sea", null], ["gold", 8],
    ["fog", null], ["fog", null], ["desert", null], ["fog", null]];
  const tiles: Tile[] = cells.map(([q, r], index) => {
    let [terrain, number] = examples[index % examples.length];
    if (mode === "hidden") { terrain = "fog"; number = null; }
    if (mode === "normal") { terrain = index % 2 ? "fields" : "forest"; number = 5; }
    return { index, q, r, center: [size * Math.sqrt(3) * (q + r / 2), size * 1.5 * r], terrain, number,
      ...(mode === "normal" ? {} : { visibility: terrain === "fog" ? "hidden" as const : "revealed" as const }) };
  });
  // Geometry is public fixture scaffolding, not a game map generator or a legality calculation.
  const vertices: Record<string, [number, number]> = {}, ids = new Map<string, number>();
  const edges: EdgeTuple[] = [], edge_adj_hexes: Record<string, number[]> = {};
  for (const tile of tiles) {
    const corners = Array.from({ length: 6 }, (_, i) => {
      const angle = (60 * i - 30) * Math.PI / 180;
      const point: [number, number] = [tile.center![0] + size * Math.cos(angle), tile.center![1] + size * Math.sin(angle)];
      const key = point.map(n => n.toFixed(5).replace("-0.00000", "0.00000")).join(",");
      if (!ids.has(key)) { ids.set(key, ids.size); vertices[String(ids.get(key))] = point; }
      return ids.get(key)!;
    });
    corners.forEach((v, i) => {
      const edge: EdgeTuple = [v, corners[(i + 1) % 6]].sort((a, b) => a - b) as EdgeTuple;
      const key = edge.join(",");
      if (!edge_adj_hexes[key]) { edges.push(edge); edge_adj_hexes[key] = []; }
      edge_adj_hexes[key].push(tile.index!);
    });
  }
  const coast = edges.find(e => edge_adj_hexes[e.join(",")].includes(0) && edge_adj_hexes[e.join(",")].includes(1))!;
  const outer = edges.find(e => edge_adj_hexes[e.join(",")].length === 1 && edge_adj_hexes[e.join(",")][0] === 5);
  const road = edges.find(e => !e.every(v => coast.includes(v)) && edge_adj_hexes[e.join(",")].includes(0))!;
  const ship = edges.find(e => !e.every(v => coast.includes(v)) && edge_adj_hexes[e.join(",")].includes(1))!;
  const city = vertices[String(coast[0])] ? coast[0] : road[0];
  const settlement = edges.find(e => edge_adj_hexes[e.join(",")].includes(2) && !e.includes(city))![0];
  const candidateRoad = edges.find(e => e.join(",") !== road.join(",") && e.join(",") !== ship.join(","))!;
  const candidateShip = edges.find(e => e.join(",") !== road.join(",") && e.join(",") !== ship.join(",") && e.join(",") !== candidateRoad.join(","))!;
  return {
    tiles, size, vertices, edges, edge_adj_hexes,
    occupied_v: { [city]: [1, 2], [settlement]: [0, 1] },
    occupied_e: { [road.join(",")]: 0 }, occupied_ships: { [ship.join(",")]: 0 },
    ports: mode === "hidden" || mode === "large" ? [] : [[coast, "2:1:wood"], ...(outer ? [[outer, "3:1"] as [EdgeTuple, string]] : [])],
    robber_tile: mode === "hidden" ? -1 : 5, robbers: mode === "hidden" ? [] : [5], pirate_tile: mode === "normal" || mode === "hidden" ? null : 1,
    scenario: { rules: { starting_islands: null, new_island_vp: 0, ...(mode === "normal" ? {} : { fog: { profile: "shared-preassigned-v1" } }) },
      home_islands: {}, awarded_islands: {}, ...(mode === "normal" ? {} : { fog: { visibility: "shared" } }) },
    rules_config: { enable_seafarers: mode !== "normal", enable_move_ship: true, enable_pirate: true, enable_gold: true, target_vp: 10 },
    phase: "main", turn: 0, rolled: true, you_pid: 0, pending_action: null, pending_pid: null, pending_gold: {}, discard_required: {},
    bank_available: { wood: true, brick: true, sheep: true, wheat: true, ore: true }, free_roads: {},
    map_meta: { name: "Synthetic public Fog fixture" },
    players: [{ pid: 0, name: "Explorer", color: "red", vp: 2, resource_count: 10, dev_count: 0,
      res: { wood: 2, brick: 2, sheep: 2, wheat: 2, ore: 2 }, dev_cards: [] },
      { pid: 1, name: "Observer", color: "blue", vp: 2, resource_count: 4, dev_count: 1 }],
    legal: { pid: 0, settlements: [candidateRoad[0]], roads: [candidateRoad], ships: [candidateShip], cities: [settlement],
      robber_tiles: [], pirate_tiles: [], robber_victims: {}, pirate_victims: {},
      move_ship: { sources: [ship], targets: { [ship.join(",")]: [candidateShip] } } },
    game_events: [],
  };
}

export function goldDiscoveryFixture(): GameSnapshot {
  const state = publicFogFixture();
  state.pending_action = "choose_gold"; state.pending_pid = 0; state.pending_gold = { "0": 1 };
  state.legal = { pid: 0, roads: [], ships: [], cities: [], settlements: [], robber_tiles: [], pirate_tiles: [] };
  state.game_events = [{ id: 1, tick: 2, at_ms: 1000, type: "build_ship", actor_pid: 0 },
    { id: 2, tick: 2, at_ms: 1000, type: "discover_tile", actor_pid: 0, tile: 2, terrain: "gold", number: 8,
      reward: { kind: "gold_choice", quantity: 1 } }];
  return state;
}
