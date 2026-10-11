import { publicTileVisual } from "../board/publicTiles";
import type { Tile } from "../components/BoardView.types";
import type { GameplayEvent } from "../wsClient";
import type { GameSnapshot } from "./presentation";

/** Only describe events whose contents are already present in the current public tile. */
export function isPublicDiscovery(event: GameplayEvent, tiles: Tile[]): boolean {
  if (event.type !== "discover_tile" || !Number.isInteger(event.tile) || event.tile! < 0
    || event.tile! >= tiles.length || !Number.isInteger(event.actor_pid) || event.actor_pid < 0) return false;
  const tile = publicTileVisual(tiles[event.tile!]);
  return tile.visibility === "revealed" && event.terrain === tile.terrain && (event.number ?? null) === tile.number;
}

export function discoveryRewardText(reward: GameplayEvent["reward"]): string {
  if (!reward || ![0, 1].includes(reward.quantity)) return "";
  switch (reward.kind) {
    case "none": return reward.quantity === 0 ? "; no discovery reward" : "";
    case "gold_choice": return reward.quantity ? "; reward: choose 1 resource from the bank" : "; gold reward unavailable";
    case "resource": return ["wood", "brick", "sheep", "wheat", "ore"].includes(reward.resource)
      ? reward.quantity ? `; reward: 1 ${reward.resource}` : `; ${reward.resource} reward unavailable` : "";
    default: return "";
  }
}

/** Explain the existing personal pending choice, without reading a private discovery ledger. */
export function goldDiscoveryReason(state: GameSnapshot, pid: number): string | null {
  if (state.pending_action !== "choose_gold" || !(state.pending_gold?.[String(pid)] > 0)) return null;
  const events = state.game_events ?? [];
  // Partial Gold choices may add later choose_gold events. Their initiating
  // command still identifies the discovery batch; an older completed batch cannot qualify.
  const initiating = [...events].reverse().find(e => e.type !== "choose_gold");
  return initiating && events.some(e => e.tick === initiating.tick && e.actor_pid === pid
    && isPublicDiscovery(e, state.tiles) && e.reward?.kind === "gold_choice" && e.reward.quantity === 1)
    ? "Discovery reward: choose resources from the bank to finish exploring and continue your action." : null;
}
