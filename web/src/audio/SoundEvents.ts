import type { GameplayEvent, MatchState, TradeOffer } from "../wsClient";
import { DICE_SETTLED_MS } from "../game/dice";
import type { SoundCue } from "./sounds";

export type SoundRequest = { id: string; cue: SoundCue; delay?: number; priority?: number };
export type SoundFrame = { key: string; tick: number; state: MatchState["state"]; pid: number; live: boolean;
  freshStart?: boolean; reduced?: boolean; diceElapsed?: number };
export type SoundCursor = { key: string; tick: number; lastId: number; live: boolean; pid: number;
  turn: number; phase: string; gameOver: boolean; offers: TradeOffer[]; handCount: number };
const EVENT_CUES: Record<string, SoundCue> = {
  place_road: "road", place_settlement: "settlement", upgrade_city: "city", build_ship: "ship", move_ship: "ship_move",
  trade_bank: "bank_trade", buy_dev: "dev_buy", play_dev: "dev_play", move_robber: "robber", move_pirate: "pirate", theft: "theft",
};
// The mapper deliberately never reads resources/resource/card: an observer's theft sounds identical.
export function eventSound(event: GameplayEvent): SoundCue | undefined { return EVENT_CUES[event.type]; }
const relevant = (offer: TradeOffer, pid: number) => offer.from_pid === pid || offer.to_pid === pid || offer.to_pid === null;

/** Consume committed recipient-filtered facts; own totals only qualify a generic confirmed gain. */
export function collectSoundEvents(previous: SoundCursor | null, frame: SoundFrame): { cursor: SoundCursor; sounds: SoundRequest[] } {
  const { state, key, pid, live } = frame, same = previous?.key === key;
  const events = state.game_events ?? [], lastId = Math.max(same ? previous.lastId : 0, 0, ...events.map(e => e.id));
  const player = state.players?.find(p => p.pid === pid);
  const handCount = player && "resource_count" in player && typeof player.resource_count === "number" ? player.resource_count : 0;
  const cursor: SoundCursor = { key, tick: Math.max(same ? previous.tick : 0, frame.tick), lastId, live, pid,
    turn: state.turn, phase: state.phase, gameOver: !!state.game_over, offers: state.trade_offers ?? [],
    handCount };
  if (same && frame.tick < previous.tick) return { cursor: previous, sounds: [] };
  const sounds: SoundRequest[] = [], add = (cue: SoundCue, id: string, delay = 0, priority = 3) => {
    if (!sounds.some(s => s.id === id)) sounds.push({ cue, id, delay, priority });
  };
  if (!previous || !same || previous.pid !== pid) {
    if (live && !state.game_over && (frame.freshStart || (previous?.live && !same))) add("game_start", `${key}:start`, 0, 5);
    return { cursor, sounds };
  }
  if (!live || !previous.live) return { cursor, sounds };
  const fresh = events.filter(event => event.id > previous.lastId);
  const landing = frame.reduced ? 0 : Math.max(0, DICE_SETTLED_MS - (frame.diceElapsed ?? 0));
  for (const event of fresh) {
    const id = `${key}:${event.id}`;
    if (event.type === "roll") {
      if (!frame.reduced) add("dice_roll", `${id}:roll`, 0, 4);
      add("dice_land", `${id}:land`, landing, 4);
    } else if (event.type === "production" && (event.quantity ?? 0) > 0) {
      add("production", `${key}:${event.tick}:production`, landing + 70, 1);
      if (event.player_pid === pid) add("hand", `${key}:${event.tick}:hand`, landing + 640, 1);
    } else {
      const cue = eventSound(event);
      if (cue) add(cue, id);
      if (["choose_gold", "trade_bank"].includes(event.type) && event.actor_pid === pid)
        add("hand", `${key}:${event.tick}:hand`, 140, 1);
      if (event.type === "play_dev" && event.actor_pid === pid && cursor.handCount > previous.handCount)
        add("hand", `${key}:${event.tick}:hand`, 140, 1);
    }
  }
  for (const offer of cursor.offers) {
    const old = previous.offers.find(o => o.offer_id === offer.offer_id);
    if (!relevant(offer, pid)) continue;
    if (!old && offer.status === "active" && offer.from_pid !== pid) add("trade_offer", `${key}:offer:${offer.offer_id}`, 0, 4);
    if (old?.status === "active" && offer.status === "accepted") {
      add("trade_accept", `${key}:accepted:${offer.offer_id}`);
      if (offer.from_pid === pid || fresh.some(event => event.type === "trade_offer_accept" && event.actor_pid === pid))
        add("hand", `${key}:${frame.tick}:hand`, 140, 1);
    }
    if (old?.status === "active" && ["declined", "canceled"].includes(offer.status))
      add("trade_cancel", `${key}:closed:${offer.offer_id}`, 0, 2);
  }
  if (!state.game_over && state.phase === "main" && state.turn === pid && (previous.turn !== pid || previous.phase !== "main"))
    add("turn", `${key}:turn:${frame.tick}`, 100, 4);
  if (!previous.gameOver && state.game_over)
    add(state.winner_pid === pid ? "victory" : "game_over", `${key}:result`, 120, 7);
  return { cursor, sounds };
}
