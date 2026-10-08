import { useEffect } from "react";
import type { BoardInteraction } from "./interaction";
import { buildTools, type GameSnapshot } from "../game/presentation";
import GameIcon from "../game/GameIcon";
import GameOverlay from "../game/GameOverlay";
import ActionButton from "../game/ActionButton";
import { phaseReason, shipsEnabled } from "../game/actions";
import { costPreview, type CostAction } from "../game/costs";

export function buildUnavailableReason(state: GameSnapshot, interaction: BoardInteraction, action: CostAction,
  resources: Record<string, number>) {
  if (interaction.selection.waiting) return "Waiting for server confirmation.";
  if (interaction.selection.victim) return "Complete the player choice first.";
  if (!interaction.legal) return "Waiting for server availability.";
  if (state.phase === "setup") return state.turn !== interaction.legal.pid ? "Wait for your turn."
    : state.pending_action ? "Resolve the pending choice first." : "No legal placement targets available.";
  const free = (action === "road" || action === "ship") && !!interaction.legal.road_free;
  const reason = phaseReason(state, interaction.legal.pid, !free);
  if (reason) return reason;
  const missing = costPreview(action, resources, free)
    .filter(cost => !cost.available).map(cost => `${cost.quantity - (resources[cost.resource] ?? 0)} ${cost.resource}`);
  if (missing.length) return `Missing resources: ${missing.join(", ")}.`;
  return action === "city" ? "No settlements available to upgrade."
    : `No legal ${action === "road" || action === "ship" ? "edges" : "vertices"} available.`;
}

/** Direct presentation of the existing server targets and shared-controller tools. */
export default function BoardControls({ state, interaction, resources = {} }: {
  state: GameSnapshot; interaction: BoardInteraction; resources?: Record<string, number>;
}) {
  const { legal, action, selection } = interaction;
  const blocked = selection.waiting || !!selection.victim;
  const tools = buildTools(interaction).filter(t => t.id !== "ship" || shipsEnabled(state));
  const movement = !!(legal?.robber_tiles?.length || legal?.pirate_tiles?.length);
  const setupTools = state.setup_need === "settlement"
    ? tools.filter(tool => tool.id === "settlement")
    : tools.filter(tool => tool.id === "road" || tool.id === "ship");
  useEffect(() => {
    if (state.phase === "setup" || blocked || !action || movement) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || document.querySelector('[role="dialog"]')
        || (event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable="true"]'))) return;
      event.preventDefault();
      if (selection.shipSource) interaction.onCancel();
      else interaction.onSelectAction(null);
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [state.phase, blocked, action, movement, selection.shipSource, interaction.onCancel, interaction.onSelectAction]);
  return <div className="board-controls" role="group" aria-label="Board actions" data-movement={movement}>
    {state.phase === "setup" ? setupTools.map(tool => <ActionButton key={tool.id} action={tool.id as CostAction}
      label={tool.label} resources={resources} free selected={action === tool.id}
      disabled={blocked || !tool.count}
      reason={blocked || !tool.count ? buildUnavailableReason(state, interaction, tool.id as CostAction, resources) : null}
      onClick={() => interaction.onSelectAction(tool.id)} />)
      : !movement && tools.map(tool => <ActionButton key={tool.id} action={tool.id as CostAction}
        label={tool.label} resources={resources} selected={action === tool.id}
        free={(tool.id === "road" || tool.id === "ship") && !!legal?.road_free} disabled={blocked || !tool.count}
        reason={blocked || !tool.count ? buildUnavailableReason(state, interaction, tool.id as CostAction, resources) : null}
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
