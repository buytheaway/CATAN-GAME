import type { GameSnapshot } from "../../src/game/presentation";
import { publicBuildingFixture } from "./publicBuildings";

export type ThreatPreviewKind = "robber" | "pirate";

/** Only public synthetic geometry/state; never an assignment or a legality evaluator. */
export function publicThreatFixture(large = false) {
  const state = publicBuildingFixture(large);
  // Two already-public adjacent sea tiles permit an honest short visual segment.
  state.tiles[6] = { ...state.tiles[6], visibility: "revealed", terrain: "sea", number: null };
  state.robber_tile = 5; state.robbers = [5]; state.pirate_tile = 1;
  state.legal = { ...state.legal!, robber_tiles: [0, 2, 5], pirate_tiles: [1, 6],
    robber_victims: {}, pirate_victims: {} };
  state.map_meta = { name: "Synthetic public robber and pirate preview" };
  return state;
}

/** Publishes facts only. The server—not this display fixture—decides real moves/theft. */
export function threatPreviewChange(state: GameSnapshot, kind: ThreatPreviewKind, tick: number, theft = false) {
  const from = kind === "robber" ? state.robber_tile : state.pirate_tile;
  const to = kind === "robber" ? from === 5 ? 0 : 5 : from === 1 ? 6 : 1;
  if (kind === "robber") { state.robber_tile = to; state.robbers = [to]; }
  else state.pirate_tile = to;
  const events = state.game_events ?? (state.game_events = []);
  events.push({ id: (events.at(-1)?.id ?? 0) + 1, tick, at_ms: Date.now(),
    actor_pid: 0, type: "move_" + kind, from_tile: from ?? undefined, tile: to });
  if (theft) events.push({ id: events.at(-1)!.id + 1, tick, at_ms: Date.now(),
    actor_pid: 0, type: "theft", victim_pid: 1, quantity: 1 });
  return { from, to };
}
