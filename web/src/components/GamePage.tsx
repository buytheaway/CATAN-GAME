import { useCallback, useEffect, useRef, useState } from "react";
import type { MatchState, RoomState, ServerError, WSClient } from "../wsClient";
import BoardRenderer from "./BoardRenderer";
import BoardControls from "../board/BoardControls";
import { useBoardInteraction } from "../board/useBoardInteraction";
import { ContextPrompt, GameTopBar, ResourceHand } from "../game/GameHUD";
import GameOverlay from "../game/GameOverlay";
import GameIcon from "../game/GameIcon";
import { RESOURCES, turnActions, type GameSnapshot } from "../game/presentation";
import TradePanel, { IncomingTrades } from "../game/TradePanel";
import DevelopmentPanel, { DevelopmentHand } from "../game/DevelopmentCards";
import Endgame from "../game/Endgame";
import { addressedOffers, type DevType } from "../game/actions";
import { useGameCommand } from "../game/useGameCommand";
import "../game/game.css";

export default function GamePage({ client, match, room, status, log, error, onBackToLobby }: {
  client: WSClient; match: MatchState; room: RoomState | null; status: string; log: string[]; error: ServerError | null;
  onBackToLobby?: () => void;
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
  const [drawer, setDrawer] = useState<"log" | "info" | "trade" | "dev" | null>(null);
  const [selectedDev, setSelectedDev] = useState<DevType | null>(null);
  const [dismissedOffers, setDismissedOffers] = useState<number[]>([]);
  const closeDrawer = useCallback(() => setDrawer(null), []);
  const matchKey = `${match.room_code}:${match.match_id}`;
  const request = useGameCommand(client, matchKey);
  const interaction = useBoardInteraction(state, youPid, matchKey, error,
    cmd => client.sendCmd(cmd));
  const freeRoads = state.free_roads?.[String(youPid)] ?? 0;
  const previousFree = useRef(0);
  useEffect(() => {
    setDrawer(null); setSelectedDev(null); setDismissedOffers([]); previousFree.current = 0;
  }, [matchKey]);
  useEffect(() => { if (state.pending_action || state.game_over) setDrawer(null); }, [state.pending_action, state.game_over]);
  useEffect(() => {
    // Let the shared controller reconcile the board ACK before changing tools.
    if (interaction.selection.waiting) return;
    if (freeRoads > previousFree.current) interaction.onSelectAction("road");
    else if (freeRoads === 0 && previousFree.current > 0 && interaction.action === "road") interaction.onSelectAction(null);
    previousFree.current = freeRoads;
  }, [freeRoads, matchKey, youPid, interaction.selection.waiting]);
  const { canRoll, canEnd } = turnActions(state, youPid);
  const ordinaryActions = state.phase === "main" && pending === "none" && !state.game_over;
  const mandatoryChoice = needGold || needDiscard || !!interaction.selection.victim;
  const incoming = addressedOffers(state, youPid).filter(o => !dismissedOffers.includes(o.offer_id));
  const blocked = request.waiting || status !== "connected";
  const openDev = (type: DevType | null) => {
    setSelectedDev(type); interaction.onSelectAction(null); setDrawer("dev");
  };

  return <main className="game-shell">
    <GameTopBar state={state} pid={youPid} roomCode={match.room_code} drawer={drawer === "info" || drawer === "log" ? drawer : null}
      onInfo={() => setDrawer(current => current === "info" ? null : "info")}
      onLog={() => setDrawer(current => current === "log" ? null : "log")} />
    <section className="board-stage" aria-label="Game board">
      <ContextPrompt state={state} pid={youPid} interaction={interaction} />
      <div className="board-command-surface" style={{ height: "100%", pointerEvents: blocked ? "none" : undefined }}
        aria-busy={request.waiting}><BoardRenderer state={state} interaction={interaction} /></div>
      {error && <div className="game-error error" role="alert">{error.message}</div>}
      {status !== "connected" && <div className="connection-notice" role="status">Connection: {status}</div>}
    </section>
    <footer className="game-bottom-hud">
      <div className="personal-hands"><ResourceHand resources={res} />
        <DevelopmentHand state={state} pid={youPid} onCard={openDev} /></div>
      <section className="action-dock" aria-label="Actions">
        <div className="hud-caption">{state.phase === "setup" ? "Starting placements" : "Your actions"}
          {state.last_roll != null && <span className="last-roll"><GameIcon name="roll" /> Last roll {state.last_roll}</span>}
        </div>
        <div className="dock-buttons">
          {ordinaryActions && <button className="game-button primary-action" disabled={!canRoll || blocked}
            onClick={() => client.sendCmd({ type: "roll" })}><GameIcon name="roll" /><span>Roll</span></button>}
          {!state.game_over && <BoardControls state={state} interaction={{ ...interaction,
            selection: { ...interaction.selection, waiting: interaction.selection.waiting || blocked } }} />}
          {ordinaryActions && <>
            <button className="game-button" disabled={blocked} aria-label="Trade" aria-haspopup="dialog"
              onClick={() => { interaction.onSelectAction(null); setDrawer("trade"); }}>
              <GameIcon name="trade" /><span>Trade</span></button>
            <button className="game-button" disabled={blocked} aria-haspopup="dialog" onClick={() => openDev(null)}>
              <GameIcon name="dev" /><span>Dev Card</span></button>
            <button className="game-button end-action" disabled={!canEnd || blocked}
              onClick={() => client.sendCmd({ type: "end_turn" })}><GameIcon name="end" /><span>End Turn</span></button>
          </>}
        </div>
      </section>
    </footer>

    {(drawer === "log" || drawer === "info") && !mandatoryChoice && !state.game_over && <GameOverlay key={drawer} id={`game-${drawer}`}
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

    {drawer === "trade" && !mandatoryChoice && !state.game_over && <TradePanel key={matchKey} state={state} pid={youPid}
      submit={request.submit} waiting={blocked} error={error} onClose={closeDrawer} />}
    {drawer === "dev" && !mandatoryChoice && !state.game_over && <DevelopmentPanel key={`${matchKey}:${selectedDev ?? "all"}`}
      state={state} pid={youPid} selected={selectedDev} submit={request.submit} waiting={blocked} error={error}
      onClose={closeDrawer} onBoardPlay={closeDrawer} />}
    {!drawer && !mandatoryChoice && !state.pending_action && !state.game_over && incoming.length > 0 &&
      <IncomingTrades state={state} pid={youPid} offers={incoming} submit={request.submit} waiting={blocked} error={error}
        onClose={() => setDismissedOffers(ids => [...ids, ...incoming.map(o => o.offer_id)])} />}
    {state.game_over && <Endgame key={matchKey} state={state} pid={youPid} room={room} connected={status === "connected"}
      matchKey={matchKey} error={error} onRematch={() => client.rematch()} onLobby={onBackToLobby} />}

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
