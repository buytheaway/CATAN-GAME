import type { GameState } from "../components/BoardView.types";
import type { BoardInteraction } from "./interaction";
import { buildTools } from "../game/presentation";
import GameIcon from "../game/GameIcon";
import GameOverlay from "../game/GameOverlay";
import ActionButton from "../game/ActionButton";
import { shipsEnabled } from "../game/actions";
import type { CostAction } from "../game/costs";

/** Direct presentation of the existing server targets and shared-controller tools. */
export default function BoardControls({ state, interaction, resources = {} }: {
  state: GameState; interaction: BoardInteraction; resources?: Record<string, number>;
}) {
  const { legal, action, selection } = interaction;
  const blocked = selection.waiting || !!selection.victim;
  const tools = buildTools(interaction).filter(t => t.id !== "ship" || shipsEnabled(state));
  const movement = !!(legal?.robber_tiles?.length || legal?.pirate_tiles?.length);
  return <div className="board-controls" role="group" aria-label="Board actions" data-movement={movement}>
    {state.phase === "setup" ? <ActionButton action={state.setup_need === "settlement" ? "settlement" : "road"}
      label={state.setup_need === "settlement" ? "Settlement" : "Road"} resources={resources} free selected
      disabled={blocked || !(state.setup_need === "settlement" ? legal?.settlements.length : legal?.roads.length)}
      onClick={() => interaction.onSelectAction(state.setup_need === "settlement" ? "settlement" : "road")} />
      : !movement && tools.map(tool => <ActionButton key={tool.id} action={tool.id as CostAction}
        label={tool.label} resources={resources} selected={action === tool.id}
        free={tool.id === "road" && !!legal?.road_free} disabled={blocked || !tool.count}
        reason={!tool.count ? "No available targets in the current state." : null}
        onClick={() => interaction.onSelectAction(action === tool.id ? null : tool.id)} />)}
    <div className="board-context-actions">
      {!movement && state.phase !== "setup" && shipsEnabled(state) && !!legal?.move_ship?.sources.length
        && state.rules_config?.enable_move_ship && <button className="game-button"
        aria-pressed={action === "move_ship"} disabled={blocked}
        onClick={() => interaction.onSelectAction(action === "move_ship" ? null : "move_ship")}>
        <GameIcon name="move_ship" /><span>Move Ship</span></button>}
    {movement && <>
      {!!legal?.robber_tiles?.length && <button className="game-button" aria-pressed={action === "robber"} disabled={blocked}
        onClick={() => interaction.onSelectAction(action === "robber" ? null : "robber")}>
        <GameIcon name="robber" /><span>Robber</span></button>}
      {!!legal?.pirate_tiles?.length && state.rules_config?.enable_pirate && <button className="game-button"
        aria-pressed={action === "pirate"} disabled={blocked}
        onClick={() => interaction.onSelectAction(action === "pirate" ? null : "pirate")}>
        <GameIcon name="pirate" /><span>Pirate</span></button>}
      <span className="sr-only">Click land for robber or sea for pirate.</span>
    </>}
    {selection.shipSource ? <button className="game-button cancel-action" onClick={interaction.onCancel}>Cancel move</button>
      : action && state.phase !== "setup" && !blocked && <button className="game-button cancel-action"
        onClick={() => interaction.onSelectAction(null)}>Cancel</button>}
    </div>
    {selection.victim && <GameOverlay id="victim-choice" title="Choose player" onClose={interaction.onCancel}>
      <strong>Choose player to steal from</strong>
      <div className="victim-options">{selection.victim.victims.map(pid => <button key={pid} className="game-button"
        onClick={() => interaction.onVictimClick(pid)}>{state.players?.find(p => p.pid === pid)?.name ?? `P${pid + 1}`}</button>)}
        <button className="game-button" onClick={interaction.onCancel}>Cancel</button>
      </div>
    </GameOverlay>}
  </div>;
}
