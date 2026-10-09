import type { CSSProperties, ReactNode } from "react";
import { colorForPlayer } from "../board/colors";
import type { BoardInteraction } from "../board/interaction";
import type { GameSnapshot } from "./presentation";
import { contextPrompt, RESOURCES } from "./presentation";
import GameIcon from "./GameIcon";
import ResourceCard from "./ResourceCard";
import type { Resource } from "./actions";
import TurnTimer from "./TurnTimer";
import { AccountControls } from "../auth/AuthUI";
import type { RoomState } from "../wsClient";
import { StatusBadge } from "../shell/PageShell";

export function GameTopBar({ state, roomCode, onInfo, onLog, drawer, status = "connected", logOpen = false, onTest, testAvailable = false, waiting = false, audioControls }: {
  state: GameSnapshot; pid: number; roomCode: string; drawer: string | null; onInfo: () => void; onLog: () => void;
  status?: string; logOpen?: boolean; onTest?: () => void; testAvailable?: boolean; waiting?: boolean;
  audioControls?: ReactNode;
}) {
  return <header className="game-topbar">
    <div className="game-brand"><strong>CATAN.КОЛОНИЗАТОРЫ</strong>
      <span className="game-room" title={`${state.map_meta?.name ?? state.map_id ?? "Current map"} · Room ${roomCode}`}>
        {state.map_meta?.name ?? state.map_id ?? "Current map"}<span className="game-room-code"> · {roomCode}</span></span></div>
    <div className="match-summary"><span className="vp-goal">Goal <strong>{state.rules_config?.target_vp ?? 10} VP</strong></span>
      <span className="match-connection" role="status"><StatusBadge tone={status === "connected" ? "live" : "neutral"}>
        {status === "connected" ? "Online" : status === "reconnecting" ? "Reconnecting…" : status}
      </StatusBadge></span>
      <AccountControls />
      {audioControls}
      {state.test_mode && (state.test_tools && onTest
        ? <button className="game-button test-mode-entry" aria-label="Test Tools" title="Non-production Test Room · open developer tools"
          disabled={!testAvailable || waiting} onClick={onTest}><b>TEST MODE</b><span>Tools</span></button>
        : <span className="test-room-warning" title="Non-production Test Room · host-only tools">TEST MODE</span>)}
      <button className="game-button icon-button" aria-label="Game info" aria-expanded={drawer === "info"}
        aria-controls="game-info" onClick={onInfo}><GameIcon name="info" /></button>
      <button className="game-button icon-button" aria-label="Event log" aria-expanded={logOpen}
        aria-controls="game-log" onClick={onLog}><GameIcon name="log" /></button>
    </div>
  </header>;
}

export function PlayerStrip({ state, pid, room }: { state: GameSnapshot; pid: number; room?: RoomState | null }) {
  return <ol className="players-strip" aria-label="Players">
      {state.players.map(p => {
        const presence = room?.players.find(slot => slot.pid === p.pid);
        return <li key={p.pid} className={`player-hud${state.turn === p.pid ? " is-current" : ""}`}
        data-motion-anchor={p.pid}
        style={{ "--player-color": colorForPlayer(p.pid, state.players) } as CSSProperties}
        aria-current={state.turn === p.pid ? "true" : undefined}>
        <span className="player-identity"><span className="player-number">{p.pid + 1}</span>
          {presence && <span className={`player-presence${presence.connected ? " is-online" : ""}`}
            aria-label={presence.connected ? "Connected" : "Disconnected"} title={presence.connected ? "Connected" : "Disconnected"} />}</span>
        <div className="player-hud-details"><div className="player-name"><strong title={p.name}>{p.name}</strong>
          {p.pid === pid && <span>you</span>}{room?.host_pid === p.pid && <span className="player-role">host</span>}</div>
          <div className="player-counters"><strong>{p.vp} VP</strong>
            <span aria-label={`${p.resource_count} resource cards`}>{p.resource_count} cards</span>
            <span aria-label={`${p.dev_count} development cards`}>{p.dev_count} dev</span>
          </div>
          {!!p.special_vp && <div className="player-counters"><span title="Island bonus included in total VP">
            {p.special_vp} island VP</span></div>}
        </div>
        {state.turn === p.pid && <div className="turn-status"><span className="turn-indicator">{p.pid === pid ? "Your turn" : "Turn"}</span>
          <TurnTimer timer={state.turn_timer} /></div>}
      </li>; })}
    </ol>;
}

export function ContextPrompt({ state, pid, interaction }: { state: GameSnapshot; pid: number; interaction: BoardInteraction }) {
  const prompt = contextPrompt(state, pid, interaction);
  return <div className="context-prompt" role="status" aria-live="polite">
    <span className="context-eyebrow">{state.turn === pid ? "Your table" : "At the table"}</span>
    <strong>{prompt.title}</strong><span>{prompt.detail}</span>
  </div>;
}

export function ScenarioSummary({ state }: { state: GameSnapshot }) {
  const rules = state.scenario?.rules;
  if (!rules || (!rules.starting_islands && !rules.new_island_vp)) return null;
  return <section aria-label="Scenario rules">
    <strong>Island rules</strong>
    <p>{rules.starting_islands
      ? "Opening settlements must be on the designated starting islands. Follow the highlighted targets."
      : "Opening settlements may be on any island."}</p>
    {!!rules.new_island_vp && <p>Earn {rules.new_island_vp} extra VP for your first settlement on each island
      where you did not place an opening settlement. Each player can earn this bonus once per island.
      City upgrades give no extra island bonus.</p>}
  </section>;
}

export function ResourceHand({ resources, onResource, disabled = false }: {
  resources: Record<string, number>; onResource?: (resource: Resource) => void; disabled?: boolean;
}) {
  return <section className="resource-hand" aria-label="Your resource hand" data-motion-anchor="hand">
    <div className="hud-caption">Your hand</div>
    <div className="resource-cards">{RESOURCES.map(resource => <ResourceCard key={resource}
      resource={resource} count={resources[resource] ?? 0} disabled={disabled || !resources[resource]}
      onClick={onResource ? () => onResource(resource) : undefined}
      label={onResource ? `Give ${resource} (${resources[resource] ?? 0} owned)` : undefined} />)}</div>
  </section>;
}

export function BankSummary({ available, counts }: {
  available: Record<string, boolean> | undefined; counts?: Record<string, number>;
}) {
  return <details className="bank-summary" open><summary data-motion-anchor="bank">{counts ? "Bank" : "Bank availability"}</summary>
    <div className="bank-resources">{RESOURCES.map(resource => <span key={resource}
      className={`bank-resource resource-${resource}${available?.[resource] ? "" : " is-empty"}`}
      aria-label={`${resource}: ${counts ? counts[resource] ?? 0 : available?.[resource] ? "available" : "unavailable"}`}>
      {counts ? <GameIcon name={resource} /> : <span className="bank-card-back">?</span>}<small>{counts ? counts[resource] ?? 0 : available?.[resource] ? "Available" : "Empty"}</small>
    </span>)}</div>
    <p>{counts ? "Public counts · Development deck hidden." : "Exact bank quantities are hidden."}</p>
  </details>;
}
