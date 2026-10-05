import { useCallback, useState } from "react";
import type { MatchState, RoomState, ServerError, WSClient } from "../wsClient";
import BoardRenderer from "./BoardRenderer";
import BoardControls from "../board/BoardControls";
import { useBoardInteraction } from "../board/useBoardInteraction";
import { ContextPrompt, GameTopBar, ResourceHand } from "../game/GameHUD";
import GameOverlay from "../game/GameOverlay";
import GameIcon from "../game/GameIcon";
import { RESOURCES, turnActions, type GameSnapshot } from "../game/presentation";
import "../game/game.css";

export default function GamePage({ client, match, room, status, log, error }: {
  client: WSClient; match: MatchState; room: RoomState | null; status: string; log: string[]; error: ServerError | null;
}) {
  const state: GameSnapshot = match.state;
  const youPid = client.youPid ?? 0;
  const res = state.players.find(p => p.pid === youPid)?.res ?? {};
  const pending = state.pending_action || "none";
  const required = state.discard_required || {};
  const pendingGold = state.pending_gold || {};
  const needDiscard = pending === "discard" && required[String(youPid)] > 0;
  const goldNeed = Number(pendingGold[String(youPid)] || 0);
  const needGold = pending === "choose_gold" && goldNeed > 0;
  const mapMeta = state.map_meta || room?.map_meta || {};
  const mapId = state.map_id || room?.map_id || "";
  const rules = state.rules_config || {};
  const [discard, setDiscard] = useState<Record<string, number>>({});
  const [goldRes, setGoldRes] = useState<string>(RESOURCES[0]);
  const [goldQty, setGoldQty] = useState(1);
  const [drawer, setDrawer] = useState<"log" | "info" | null>(null);
  const closeDrawer = useCallback(() => setDrawer(null), []);
  const interaction = useBoardInteraction(state, youPid, `${match.room_code}:${match.match_id}`, error,
    cmd => client.sendCmd(cmd));
  const { canRoll, canEnd } = turnActions(state, youPid);
  const ordinaryActions = state.phase === "main" && pending === "none" && !state.game_over;
  const mandatoryChoice = needGold || needDiscard || !!interaction.selection.victim;

  return <main className="game-shell">
    <GameTopBar state={state} pid={youPid} roomCode={match.room_code} drawer={drawer}
      onInfo={() => setDrawer(current => current === "info" ? null : "info")}
      onLog={() => setDrawer(current => current === "log" ? null : "log")} />
    <section className="board-stage" aria-label="Game board">
      <ContextPrompt state={state} pid={youPid} interaction={interaction} />
      <BoardRenderer state={state} interaction={interaction} />
      {error && <div className="game-error error" role="alert">{error.message}</div>}
      {status !== "connected" && <div className="connection-notice" role="status">Connection: {status}</div>}
    </section>
    <footer className="game-bottom-hud">
      <ResourceHand resources={res} />
      <section className="action-dock" aria-label="Actions">
        <div className="hud-caption">{state.phase === "setup" ? "Starting placements" : "Your actions"}
          {state.last_roll != null && <span className="last-roll"><GameIcon name="roll" /> Last roll {state.last_roll}</span>}
        </div>
        <div className="dock-buttons">
          {ordinaryActions && <button className="game-button primary-action" disabled={!canRoll}
            onClick={() => client.sendCmd({ type: "roll" })}><GameIcon name="roll" /><span>Roll</span></button>}
          {!state.game_over && <BoardControls state={state} interaction={interaction} />}
          {ordinaryActions && <>
            <button className="game-button future-action" disabled aria-describedby="future-actions">
              <GameIcon name="trade" /><span>Trade</span></button>
            <button className="game-button future-action" disabled aria-describedby="future-actions">
              <GameIcon name="dev" /><span>Dev Card</span></button>
            <button className="game-button end-action" disabled={!canEnd}
              onClick={() => client.sendCmd({ type: "end_turn" })}><GameIcon name="end" /><span>End Turn</span></button>
            <span id="future-actions" className="sr-only">Trade and development card controls are not available in this client yet.</span>
          </>}
        </div>
      </section>
    </footer>

    {drawer && !mandatoryChoice && <GameOverlay key={drawer} id={`game-${drawer}`}
      title={drawer === "log" ? "Event log" : "Game info"} onClose={closeDrawer}>
      {drawer === "log" ? <pre className="game-log">{log.length ? log.join("\n") : "No events yet."}</pre> : <>
        <div className="info-map"><strong>{mapMeta.name || mapId || "Current map"}</strong>
          {mapMeta.description && <p>{mapMeta.description}</p>}</div>
        <dl className="game-info-list">
          <dt>Room</dt><dd>{match.room_code}</dd><dt>Match</dt><dd>{match.match_id}</dd>
          <dt>Tick</dt><dd>{match.tick}</dd><dt>Phase</dt><dd>{state.phase}</dd>
          <dt>Pending</dt><dd>{pending}</dd><dt>Connection</dt><dd>{status}</dd>
          <dt>Goal</dt><dd>{rules.target_vp ?? 10} VP</dd>
          <dt>Robbers</dt><dd>{rules.robber_count ?? state.robbers?.length ?? 1}</dd>
          <dt>Seafarers</dt><dd>{rules.enable_seafarers ? "On" : "Off"}</dd>
          <dt>Pirate</dt><dd>{rules.enable_pirate ? "On" : "Off"}</dd>
          <dt>Gold</dt><dd>{rules.enable_gold ? "On" : "Off"}</dd>
          <dt>Move ship</dt><dd>{rules.enable_move_ship ? "On" : "Off"}</dd>
        </dl>
      </>}
    </GameOverlay>}

    {needGold && <GameOverlay id="gold-choice" title={`Gold Choice: ${goldNeed}`} modal>
      <p>Choose resources from the bank.</p>
      <div className="gold-fields">
        <label className="field"><span>Resource</span><select aria-label="Gold resource" value={goldRes}
          onChange={e => setGoldRes(e.target.value)}>{RESOURCES.map(r => <option key={r} value={r}>{r}</option>)}</select></label>
        <label className="field"><span>Quantity</span><input aria-label="Gold quantity" type="number" min={1}
          max={goldNeed} value={goldQty} onChange={e => setGoldQty(Number(e.target.value))} /></label>
      </div>
      <button className="game-button primary-action" onClick={() => client.sendCmd({
        type: "choose_gold", res: goldRes, qty: Number(goldQty),
      })}>Choose</button>
    </GameOverlay>}
    {needDiscard && <GameOverlay id="discard-choice" title={`Discard Required: ${required[String(youPid)]}`} modal>
      <p>Select the cards to return to the bank.</p>
      <div className="discard-fields">{Object.keys(res).map(k => <label key={k} className="field">
        <span>{k}</span><input type="number" min={0} max={res[k]} value={discard[k] ?? 0}
          onChange={e => setDiscard({ ...discard, [k]: Number(e.target.value) })} />
      </label>)}</div>
      <button className="game-button primary-action" onClick={() => client.sendCmd({
        type: "discard", discards: discard,
      })}>Submit Discard</button>
    </GameOverlay>}
  </main>;
}
