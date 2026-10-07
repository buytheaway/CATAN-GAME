import type { GameSnapshot } from "./presentation";
import GameEvents from "./GameEvents";
import GameIcon from "./GameIcon";

/** Optional personalized gameplay history. Room chat has its own permanent sibling. */
export default function GameLog({ state, transport, open, onToggle }: {
  state: GameSnapshot; transport: string[]; open: boolean; onToggle: () => void;
}) {
  return <section className="sidebar-log" id="game-log" aria-label="Game Log">
    <button className="activity-toggle" aria-expanded={open} aria-controls="game-log-content" onClick={onToggle}>
      <GameIcon name="log" /><span>Game Log</span><small>{state.game_events?.length ?? 0} events</small>
    </button>
    {open && <div className="game-log-content" id="game-log-content">
      <GameEvents state={state} />
      <details className="transport-details"><summary>Connection details</summary>
        <pre className="game-log">{transport.slice(-20).join("\n")}</pre></details>
    </div>}
  </section>;
}
