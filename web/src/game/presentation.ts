import type { MatchState } from "../wsClient";
import type { BoardInteraction } from "../board/interaction";

// Normalize the intersected transport player array for UI iteration; no wire fields change.
export type GameSnapshot = Omit<MatchState["state"], "players"> & {
  players: Array<MatchState["state"]["players"][number]>;
  game_over?: boolean; last_roll?: number | null;
};
export const RESOURCES = ["wood", "brick", "sheep", "wheat", "ore"] as const;

/** Existing Roll/End conditions, extracted only to keep presentation consistent. */
export function turnActions(state: GameSnapshot, pid: number) {
  const clear = (state.pending_action || "none") === "none";
  return {
    canRoll: state.turn === pid && state.phase === "main" && !state.rolled && clear,
    canEnd: state.turn === pid && clear && !!state.rolled,
  };
}

export function buildTools(interaction: BoardInteraction) {
  const legal = interaction.legal;
  return [
    { id: "road", label: "Road", count: legal?.roads.length ?? 0 },
    { id: "settlement", label: "Settlement", count: legal?.settlements.length ?? 0 },
    { id: "city", label: "City", count: legal?.cities.length ?? 0 },
    { id: "ship", label: "Ship", count: legal?.ships.length ?? 0 },
  ];
}

/** Friendly wording from the snapshot/controller; no costs, legality or state-machine transitions. */
export function contextPrompt(state: GameSnapshot, pid: number, interaction: BoardInteraction) {
  const current = state.players.find(p => p.pid === state.turn)?.name || `Player ${state.turn + 1}`;
  const { action, selection, legal } = interaction;
  if (selection.waiting) return { title: "Waiting for server", detail: "Your action is being confirmed." };
  if (state.game_over) return { title: "Match complete", detail: "Final scores are shown above." };
  const discard = state.discard_required?.[String(pid)] ?? 0;
  const gold = state.pending_gold?.[String(pid)] ?? 0;
  if (state.pending_action === "discard" && discard > 0)
    return { title: `Discard ${discard} cards`, detail: "Choose the resources to return." };
  if (state.pending_action === "choose_gold" && gold > 0)
    return { title: `Choose ${gold} gold resources`, detail: "Complete your resource choice to continue." };
  if (selection.victim) return { title: "Choose a player to steal from", detail: "Select a player in the choice panel." };
  if (state.turn !== pid) return { title: `${current}'s turn`, detail: state.phase === "setup"
    ? `Waiting for a ${state.setup_need === "settlement" ? "settlement" : "road"} placement.` : "Waiting for their next action." };
  if (state.pending_action === "robber_move") return { title: action === "pirate" ? "Move the pirate"
    : action === "robber" || !legal?.pirate_tiles?.length ? "Move the robber" : "Move the robber or pirate",
    detail: "Choose a highlighted tile on the board." };
  if (state.pending_action) return { title: "Waiting for player choices", detail: "The turn continues once all choices are complete." };
  const freeRoads = state.free_roads?.[String(pid)] ?? 0;
  if (freeRoads > 0 && legal?.road_free) return { title: `Place road ${freeRoads >= 2 ? 1 : 2} of 2`,
    detail: legal.roads.length ? "Choose a highlighted edge for your free road." : "No legal road targets remain." };
  if (state.phase === "setup") return { title: state.setup_need === "settlement" ? "Place a settlement" : "Choose a road",
    detail: "Select a small highlighted target on the board." };
  if (action === "move_ship") return { title: selection.shipSource ? "Choose its destination" : "Select a ship to move",
    detail: selection.shipSource ? "Choose a highlighted edge, or cancel the move." : "Choose one of your highlighted ships." };
  if (["settlement", "road", "city", "ship"].includes(action ?? "")) return {
    title: action === "city" ? "Upgrade a settlement" : action === "road" ? "Choose a road"
      : action === "ship" ? "Build a ship" : "Place a settlement",
    detail: "Choose a highlighted target. Cancel to leave this tool.",
  };
  return state.rolled ? { title: "Your turn", detail: state.rules_config?.enable_seafarers
    ? "Trade, build, play a card, move a ship, or end your turn." : "Trade, build, play a card, or end your turn." }
    : { title: "Roll the dice", detail: "Your turn begins with a roll." };
}
