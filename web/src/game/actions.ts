import type { RoomState, TradeOffer } from "../wsClient";
import { RESOURCES, type GameSnapshot } from "./presentation";

export type Resource = typeof RESOURCES[number];
export type ResourceCounts = Partial<Record<Resource, number>>;
export const DEV_CARDS = {
  knight: { name: "Knight", icon: "robber", description: "Move the robber or pirate and choose a victim on the board." },
  road_building: { name: "Road Building", icon: "road", description: "Place two free roads using the highlighted board targets." },
  year_of_plenty: { name: "Year of Plenty", icon: "wheat", description: "Choose exactly two resources from the bank." },
  monopoly: { name: "Monopoly", icon: "trade", description: "Take the chosen resource type from the other players." },
  victory_point: { name: "Victory Point", icon: "dev", description: "One hidden victory point. Passive; no Play action." },
} as const;
export type DevType = keyof typeof DEV_CARDS;

export function personalPlayer(state: GameSnapshot, pid: number) {
  return state.players.find(p => p.pid === pid);
}

/** Presentation availability from the received snapshot. The executor still validates every command. */
export function phaseReason(state: GameSnapshot, pid: number, requireRoll = true): string | null {
  if (state.game_over) return "The match has ended.";
  if (state.phase !== "main") return "Finish initial placement first.";
  if (state.turn !== pid) return "Wait for your turn.";
  if (state.pending_action) return "Resolve the pending choice first.";
  if (requireRoll && !state.rolled) return "Roll the dice first.";
  return null;
}

export function maritimeRate(state: GameSnapshot, pid: number, resource: Resource): number {
  let rate = 4;
  for (const [[a, b], kind] of state.ports ?? []) {
    if (state.occupied_v[a]?.[0] !== pid && state.occupied_v[b]?.[0] !== pid) continue;
    const k = kind.trim().toLowerCase();
    const generic = ["3:1", "3", "generic", "any", "all", "none", "?"].includes(k)
      || ["3:1", "3/1", "3 to 1", "3to1"].some(s => k.includes(s));
    if (generic) rate = Math.min(rate, 3);
    else if (RESOURCES.find(r => k.includes(r)) === resource) rate = 2;
  }
  return rate;
}

export function bankTradeReason(state: GameSnapshot, pid: number, give: Resource, get: Resource) {
  const reason = phaseReason(state, pid);
  if (reason) return reason;
  if (give === get) return "Choose a different resource to receive.";
  if ((personalPlayer(state, pid)?.res?.[give] ?? 0) < maritimeRate(state, pid, give))
    return "You do not have enough cards to give.";
  if (!state.bank_available?.[get]) return "This resource is unavailable in the bank.";
  return null;
}

export function resourcePayload(counts: ResourceCounts): Record<string, number> {
  return Object.fromEntries(RESOURCES.filter(r => (counts[r] ?? 0) > 0).map(r => [r, counts[r]! ]));
}
export function countResources(counts: ResourceCounts) {
  return RESOURCES.reduce((n, r) => n + (counts[r] ?? 0), 0);
}
function validCounts(counts: ResourceCounts) {
  return RESOURCES.every(r => Number.isInteger(counts[r] ?? 0) && (counts[r] ?? 0) >= 0);
}
function canGive(hand: Record<string, number> | undefined, counts: Record<string, number>) {
  return Object.entries(counts).every(([r, n]) => (hand?.[r] ?? 0) >= n);
}

export function offerCreateReason(state: GameSnapshot, pid: number, give: ResourceCounts, get: ResourceCounts) {
  const reason = phaseReason(state, pid);
  if (reason) return reason;
  if (!validCounts(give) || !validCounts(get)) return "Use whole, non-negative card quantities.";
  if (!countResources(give) || !countResources(get)) return "Choose cards on both sides of the offer.";
  if (!canGive(personalPlayer(state, pid)?.res, resourcePayload(give))) return "You do not have the offered cards.";
  return null;
}

export function addressedOffers(state: GameSnapshot, pid: number): TradeOffer[] {
  return (state.trade_offers ?? []).filter(o => o.status === "active" && o.from_pid !== pid
    && (o.to_pid === null || o.to_pid === pid) && o.from_pid === state.turn);
}
export function offerResponseReason(state: GameSnapshot, pid: number, offer: TradeOffer, accept: boolean) {
  if (state.game_over || state.phase !== "main" || state.pending_action || !state.rolled)
    return "Trading is unavailable until the current action is complete.";
  if (offer.status !== "active" || offer.from_pid !== state.turn) return "This offer is closed.";
  if (offer.from_pid === pid || (offer.to_pid !== null && offer.to_pid !== pid)) return "This offer is not addressed to you.";
  if (accept && !canGive(personalPlayer(state, pid)?.res, offer.get)) return "You do not have the requested cards.";
  return null;
}

export function devHand(state: GameSnapshot, pid: number) {
  const cards = personalPlayer(state, pid)?.dev_cards ?? [];
  return (Object.keys(DEV_CARDS) as DevType[]).map(type => ({ type, ...DEV_CARDS[type],
    count: cards.filter(c => c.type === type).length,
    fresh: cards.filter(c => c.type === type && c.new).length,
  })).filter(card => card.count > 0);
}
export function devPlayReason(state: GameSnapshot, pid: number, type: DevType) {
  if (type === "victory_point") return "Passive victory point; this card is not played.";
  const reason = phaseReason(state, pid, false);
  if (reason) return reason;
  if (state.dev_played_turn?.[String(pid)] === undefined) return "Development card status is unavailable.";
  if (state.dev_played_turn[String(pid)]) return "You have already played a development card this turn.";
  const card = devHand(state, pid).find(c => c.type === type);
  if (!card) return "You do not hold this card.";
  if (card.count === card.fresh) return "Cards bought this turn become playable on your next turn.";
  return null;
}
export function buyDevReason(state: GameSnapshot, pid: number) {
  const reason = phaseReason(state, pid);
  if (reason) return reason;
  const res = personalPlayer(state, pid)?.res;
  return ["ore", "sheep", "wheat"].every(r => (res?.[r] ?? 0) >= 1) ? null : "Requires 1 Ore, 1 Sheep and 1 Wheat.";
}
export function plentyReason(state: GameSnapshot, pid: number, counts: ResourceCounts) {
  const reason = devPlayReason(state, pid, "year_of_plenty");
  if (reason) return reason;
  if (!validCounts(counts) || countResources(counts) !== 2) return "Choose exactly two resources.";
  if (RESOURCES.some(r => (counts[r] ?? 0) > 0 && !state.bank_available?.[r])) return "A chosen resource is unavailable in the bank.";
  return null;
}
export function plentyCommand(counts: ResourceCounts) {
  const chosen = RESOURCES.filter(r => (counts[r] ?? 0) > 0);
  return { type: "play_dev", card: "year_of_plenty", a: chosen[0], qa: counts[chosen[0]] ?? 0,
    b: chosen[1] ?? "", qb: chosen[1] ? counts[chosen[1]] ?? 0 : 0 };
}

export function rematchReason(room: RoomState | null, pid: number, connected: boolean) {
  if (!connected) return "Reconnect to start another match.";
  if (!room) return "Waiting for room information.";
  const participants = room.players.filter(p => p.name && p.connected);
  if (participants.length < 2) return "At least two connected players are needed.";
  const host = room.players.find(p => p.pid === room.host_pid);
  const starter = host?.connected ? host : participants[0];
  return starter?.pid === pid ? null : "Waiting for the room host to start a rematch.";
}
export function finalStandings(state: GameSnapshot) {
  return [...state.players].sort((a, b) => Number(b.pid === state.winner_pid) - Number(a.pid === state.winner_pid)
    || b.vp - a.vp || a.pid - b.pid);
}
