import { useEffect, useRef, useState } from "react";
import type { GameState } from "../components/BoardView.types";
import type { BoardInteraction } from "./interaction";
import { buildTools } from "../game/presentation";
import GameIcon from "../game/GameIcon";
import GameOverlay from "../game/GameOverlay";

/** Local palette presentation; targets/selection and every command remain in the shared controller. */
export default function BoardControls({ state, interaction }: { state: GameState; interaction: BoardInteraction }) {
  const [buildOpen, setBuildOpen] = useState(false);
  useEffect(() => setBuildOpen(false), [state.turn, state.phase, state.pending_action]);
  const buildButton = useRef<HTMLButtonElement>(null);
  const closePalette = () => { setBuildOpen(false); buildButton.current?.focus(); };
  useEffect(() => {
    if (!buildOpen) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setBuildOpen(false); buildButton.current?.focus(); }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [buildOpen]);
  const { legal, action, selection } = interaction;
  const blocked = selection.waiting || !!selection.victim;
  const tools = buildTools(interaction).filter(t => t.id !== "ship" || state.rules_config?.enable_seafarers);
  const movement = !!(legal?.robber_tiles?.length || legal?.pirate_tiles?.length);
  const isBuild = ["settlement", "road", "city", "ship"].includes(action ?? "");
  return <div className="board-controls" role="group" aria-label="Board actions">
    {state.phase === "setup" ? <span className="setup-action"><GameIcon name={state.setup_need || "settlement"} />
      {state.setup_need === "settlement" ? "Settlement" : "Road"}</span> : !movement && <>
      <div className="build-control">
        <button ref={buildButton} className={`game-button${isBuild ? " is-active" : ""}`} aria-expanded={buildOpen}
          aria-controls="build-palette" disabled={!tools.length || blocked}
          onClick={() => setBuildOpen(open => !open)}><GameIcon name="build" /><span>Build</span></button>
        {buildOpen && <div className="build-palette" id="build-palette" role="group" aria-label="Build options">
          <span className="palette-heading">Build a piece</span>
          {tools.map(tool => <button key={tool.id} className="game-button" aria-pressed={action === tool.id}
            disabled={blocked} onClick={() => {
              interaction.onSelectAction(action === tool.id ? null : tool.id); closePalette();
            }}><GameIcon name={tool.id} /><span>{tool.label}</span></button>)}
          <button className="palette-close" onClick={closePalette} aria-label="Close build palette">Close</button>
        </div>}
      </div>
      {!!legal?.move_ship?.sources.length && state.rules_config?.enable_move_ship && <button className="game-button"
        aria-pressed={action === "move_ship"} disabled={blocked}
        onClick={() => interaction.onSelectAction(action === "move_ship" ? null : "move_ship")}>
        <GameIcon name="move_ship" /><span>Move Ship</span></button>}
    </>}
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
    {selection.victim && <GameOverlay id="victim-choice" title="Choose player" onClose={interaction.onCancel}>
      <strong>Choose player to steal from</strong>
      <div className="victim-options">{selection.victim.victims.map(pid => <button key={pid} className="game-button"
        onClick={() => interaction.onVictimClick(pid)}>{state.players?.find(p => p.pid === pid)?.name ?? `P${pid + 1}`}</button>)}
        <button className="game-button" onClick={interaction.onCancel}>Cancel</button>
      </div>
    </GameOverlay>}
  </div>;
}
