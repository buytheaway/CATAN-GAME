import type { GameplayEvent } from "../wsClient";
import type { GameSnapshot } from "./presentation";

export function eventText(event: GameplayEvent, players: GameSnapshot["players"], tiles: GameSnapshot["tiles"] = []): string {
  const name = (pid = event.actor_pid) => players.find(p => p.pid === pid)?.name ?? `Player ${pid + 1}`;
  const actor = name();
  const tile = event.tile === undefined ? undefined : tiles[event.tile];
  const destination = tile ? `${tile.terrain}${tile.number ? ` (${tile.number})` : ""}` : "a new hex";
  switch (event.type) {
    case "roll": return `${actor} rolled ${event.dice?.join(" + ")} = ${event.total}`;
    case "production": return `${name(event.player_pid)} received ${event.resources
      ? Object.entries(event.resources).map(([r, n]) => `${n} ${r}`).join(", ") : `${event.quantity} resource card(s)`}`;
    case "theft": return `${actor} stole ${event.resource ? `1 ${event.resource}` : "a resource"} from ${name(event.victim_pid)}`;
    case "move_robber": return `${actor} moved the robber to ${destination}`;
    case "move_pirate": return `${actor} moved the pirate to ${destination}`;
    case "discard": return `${actor} returned ${event.quantity} cards to the bank`;
    case "buy_dev": return `${actor} bought a development card`;
    case "play_dev": return `${actor} played ${event.card?.replace(/_/g, " ")}`;
    case "trade_bank": return `${actor} traded with the bank`;
    case "choose_gold": return `${actor} collected gold resources`;
    case "debug": return `[DEBUG] ${actor}: ${event.action?.replace(/_/g, " ")}`;
    case "end_turn": return `${actor} ended their turn`;
    default: return `${actor}: ${event.type.replace(/_/g, " ")}`;
  }
}

export default function GameEvents({ state }: { state: GameSnapshot }) {
  return <ol className="gameplay-events" aria-label="Gameplay events">{state.game_events?.length
    ? [...state.game_events].reverse().map(e => <li key={e.id} data-event-type={e.type}>
      <span>{eventText(e, state.players, state.tiles)}</span><time dateTime={new Date(e.at_ms).toISOString()}>
        {new Date(e.at_ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></li>)
    : <li>No gameplay events yet.</li>}</ol>;
}
