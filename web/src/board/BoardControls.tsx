import type { GameState } from "../components/BoardView.types";
import type { BoardInteraction } from "./interaction";

export default function BoardControls({ state, interaction }: { state: GameState; interaction: BoardInteraction }) {
  const { legal, action, selection } = interaction;
  const tools: [string, string, number][] = [
    ["settlement", "Settlement", legal?.settlements.length ?? 0],
    ["road", "Road", legal?.roads.length ?? 0], ["city", "City", legal?.cities.length ?? 0],
  ];
  if (state.rules_config?.enable_seafarers) tools.push(["ship", "Ship", legal?.ships.length ?? 0]);
  if (state.rules_config?.enable_move_ship) tools.push(["move_ship", "Move Ship", legal?.move_ship?.sources.length ?? 0]);
  tools.push(["robber", "Robber", legal?.robber_tiles?.length ?? 0]);
  if (state.rules_config?.enable_pirate) tools.push(["pirate", "Pirate", legal?.pirate_tiles?.length ?? 0]);
  return <div className="board-controls">
    <div className="row" role="group" aria-label="Board actions">
      {tools.map(([tool, label, count]) => <button key={tool} className="btn" aria-pressed={action === tool}
        disabled={!count || selection.waiting || !!selection.victim}
        onClick={() => interaction.onSelectAction(action === tool ? null : tool)}>{label}</button>)}
      {selection.shipSource && <button className="btn" onClick={interaction.onCancel}>Cancel move</button>}
    </div>
    <div className="muted" aria-live="polite">
      {selection.waiting ? "Waiting for server…" : selection.shipSource ? "Choose a destination for the selected ship."
        : legal?.robber_tiles?.length || legal?.pirate_tiles?.length ? "Click land for robber or sea for pirate."
        : action ? `Select a highlighted ${action === "city" ? "settlement to upgrade" : "target"}.` : "Choose a board action."}
    </div>
    {selection.victim && <div className="card panel" role="dialog" aria-modal="false" aria-label="Choose player">
      <strong>Choose player to steal from</strong>
      <div className="row">{selection.victim.victims.map(pid => <button key={pid} className="btn"
        onClick={() => interaction.onVictimClick(pid)}>{state.players?.find(p => p.pid === pid)?.name ?? `P${pid + 1}`}</button>)}
        <button className="btn" onClick={interaction.onCancel}>Cancel</button>
      </div>
    </div>}
  </div>;
}
