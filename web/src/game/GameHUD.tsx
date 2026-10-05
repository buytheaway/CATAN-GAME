import type { CSSProperties } from "react";
import { PLAYER_COLORS } from "../board/constants";
import type { BoardInteraction } from "../board/interaction";
import type { GameSnapshot } from "./presentation";
import { contextPrompt, RESOURCES } from "./presentation";
import GameIcon from "./GameIcon";
import ResourceCard from "./ResourceCard";
import type { Resource } from "./actions";

export function GameTopBar({ state, pid, roomCode, onInfo, onLog, drawer }: {
  state: GameSnapshot; pid: number; roomCode: string; drawer: string | null; onInfo: () => void; onLog: () => void;
}) {
  return <header className="game-topbar">
    <div className="game-brand"><strong>CATAN<span> / Online</span></strong>
      <span className="game-room" title={state.map_meta?.name}>{state.map_meta?.name ?? "Room"} · {roomCode}</span></div>
    <ol className="players-strip" aria-label="Players">
      {state.players.map(p => <li key={p.pid} className={`player-hud${state.turn === p.pid ? " is-current" : ""}`}
        style={{ "--player-color": PLAYER_COLORS[p.pid] ?? "#ffffff" } as CSSProperties}
        aria-current={state.turn === p.pid ? "true" : undefined}>
        <span className="player-number">{p.pid + 1}</span>
        <div className="player-hud-details"><div className="player-name"><strong title={p.name}>{p.name}</strong><span>{p.pid === pid ? "you" : ""}</span></div>
          <div className="player-counters"><strong>{p.vp} VP</strong>
            <span aria-label={`${p.resource_count} resource cards`}>{p.resource_count} cards</span>
            <span aria-label={`${p.dev_count} development cards`}>{p.dev_count} dev</span>
          </div></div>
        {state.turn === p.pid && <span className="turn-indicator">{p.pid === pid ? "Your turn" : "Turn"}</span>}
      </li>)}
    </ol>
    <div className="match-summary"><span className="vp-goal">Goal <strong>{state.rules_config?.target_vp ?? 10} VP</strong></span>
      <button className="game-button icon-button" aria-label="Game info" aria-expanded={drawer === "info"}
        aria-controls="game-info" onClick={onInfo}><GameIcon name="info" /></button>
      <button className="game-button icon-button" aria-label="Event log" aria-expanded={drawer === "log"}
        aria-controls="game-log" onClick={onLog}><GameIcon name="log" /></button>
    </div>
  </header>;
}

export function ContextPrompt({ state, pid, interaction }: { state: GameSnapshot; pid: number; interaction: BoardInteraction }) {
  const prompt = contextPrompt(state, pid, interaction);
  return <div className="context-prompt" role="status" aria-live="polite">
    <span className="context-eyebrow">{state.turn === pid ? "Your table" : "At the table"}</span>
    <strong>{prompt.title}</strong><span>{prompt.detail}</span>
  </div>;
}

export function ResourceHand({ resources, onResource, disabled = false }: {
  resources: Record<string, number>; onResource?: (resource: Resource) => void; disabled?: boolean;
}) {
  return <section className="resource-hand" aria-label="Your resource hand">
    <div className="hud-caption">Your hand</div>
    <div className="resource-cards">{RESOURCES.map(resource => <ResourceCard key={resource}
      resource={resource} count={resources[resource] ?? 0} disabled={disabled || !resources[resource]}
      onClick={onResource ? () => onResource(resource) : undefined}
      label={onResource ? `Give ${resource} (${resources[resource] ?? 0} owned)` : undefined} />)}</div>
  </section>;
}

/** The public snapshot exposes availability, never the bank's exact card counts. */
export function BankSummary({ available }: { available: Record<string, boolean> | undefined }) {
  return <details className="bank-summary"><summary>Bank availability</summary>
    <div className="bank-resources">{RESOURCES.map(resource => <span key={resource}
      className={`bank-resource resource-${resource}${available?.[resource] ? "" : " is-empty"}`}
      aria-label={`${resource}: ${available?.[resource] ? "available" : "unavailable"}`}>
      <GameIcon name={resource} /><small>{available?.[resource] ? "Available" : "Empty"}</small>
    </span>)}</div>
    <p>Exact bank quantities are hidden.</p>
  </details>;
}
