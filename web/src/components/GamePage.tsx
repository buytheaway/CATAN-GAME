import { useCallback, useEffect, useRef, useState } from "react";
import type { MatchState, RoomState, ServerError, WSClient } from "../wsClient";
import BoardRenderer from "./BoardRenderer";
import BoardControls from "../board/BoardControls";
import { useBoardInteraction } from "../board/useBoardInteraction";
import { BankSummary, ContextPrompt, GameTopBar, ResourceHand } from "../game/GameHUD";
import GameOverlay from "../game/GameOverlay";
import GameIcon from "../game/GameIcon";
import { RESOURCES, turnActions, type GameSnapshot } from "../game/presentation";
import TradePanel, { IncomingTrades, TradeOffers } from "../game/TradePanel";
import DevelopmentPanel, { DevelopmentHand } from "../game/DevelopmentCards";
import Endgame from "../game/Endgame";
import { addHandResource, addressedOffers, buyDevReason, phaseReason, type DevType, type Resource, type TradeDraft } from "../game/actions";
import { useGameCommand } from "../game/useGameCommand";
import ActionButton from "../game/ActionButton";
import DiceHUD, { useDicePresentation } from "../game/DiceHUD";
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
  const [drawer, setDrawer] = useState<"log" | "info" | "dev" | null>(null);
  const [tradeDraft, setTradeDraft] = useState<TradeDraft | null>(null);
  const [selectedDev, setSelectedDev] = useState<DevType | null>(null);
  const [dismissedOffers, setDismissedOffers] = useState<number[]>([]);
  const closeDrawer = useCallback(() => setDrawer(null), []);
  const closeTrade = useCallback(() => setTradeDraft(null), []);
  const matchKey = `${match.room_code}:${match.match_id}`;
  const request = useGameCommand(client, matchKey);
  const dice = useDicePresentation(matchKey, state.dice, state.roll_count);
  const interaction = useBoardInteraction(state, youPid, matchKey, error,
    cmd => client.sendCmd(cmd));
  const freeRoads = state.free_roads?.[String(youPid)] ?? 0;
  const previousFree = useRef(0);
  useEffect(() => {
    setDrawer(null); setTradeDraft(null); setSelectedDev(null); setDismissedOffers([]); previousFree.current = 0;
  }, [matchKey]);
  useEffect(() => { if (state.pending_action || state.game_over) setDrawer(null); }, [state.pending_action, state.game_over]);
  useEffect(() => {
    if (state.pending_action || state.game_over || state.turn !== youPid) setTradeDraft(null);
  }, [state.pending_action, state.game_over, state.turn, youPid]);
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
  const blocked = request.waiting || interaction.selection.waiting || status !== "connected";
  const purchaseReason = buyDevReason(state, youPid);
  const tradeDisabled = blocked || !!phaseReason(state, youPid);
  const tradeTargets = room ? room.players.filter(p => p.name && p.connected) : state.players;
  const ownOffers = (state.trade_offers ?? []).filter(o => o.from_pid === youPid && o.status === "active");
  const handTrade = (resource: Resource) => {
    if (tradeDisabled || !res[resource]) return;
    setDrawer(null); interaction.onSelectAction(null);
    setTradeDraft(current => addHandResource(current, resource, res));
  };
  const openDev = (type: DevType | null) => {
    setSelectedDev(type); setTradeDraft(null); interaction.onSelectAction(null); setDrawer("dev");
  };

  return <main className="game-shell">
    <GameTopBar state={state} pid={youPid} roomCode={match.room_code} drawer={drawer === "info" || drawer === "log" ? drawer : null}
      onInfo={() => setDrawer(current => current === "info" ? null : "info")}
      onLog={() => setDrawer(current => current === "log" ? null : "log")} />
    <section className="board-stage" aria-label="Game board">
      <ContextPrompt state={state} pid={youPid} interaction={interaction} />
      <div className="board-command-surface" style={{ height: "100%", pointerEvents: blocked ? "none" : undefined }}
        aria-busy={request.waiting}><BoardRenderer state={state} interaction={interaction} diceRoll={dice.roll} /></div>
      {error && <div className="game-error error" role="alert">{error.message}</div>}
      {status !== "connected" && <div className="connection-notice" role="status">Connection: {status}</div>}
    </section>
    <footer className="game-bottom-hud">
      <div className="personal-hands">
        {tradeDraft && !mandatoryChoice && !state.game_over && <TradePanel state={state} pid={youPid}
          draft={tradeDraft} onChange={setTradeDraft} targets={tradeTargets} submit={request.submit}
          waiting={blocked} error={error} onClose={closeTrade} />}
        {!tradeDraft && !drawer && !mandatoryChoice && !state.pending_action && !state.game_over && ownOffers.length > 0 &&
          <div className="own-offer-summary" aria-label="Your open offers"><TradeOffers state={{ ...state, trade_offers: ownOffers }}
            pid={youPid} waiting={blocked} submit={request.submit} /></div>}
        <ResourceHand resources={res} onResource={handTrade} disabled={tradeDisabled} />
        <DevelopmentHand state={state} pid={youPid} onCard={openDev} /></div>
      <section className="action-dock" aria-label="Actions">
        <div className="hud-caption">{state.phase === "setup" ? "Starting placements" : "Your actions"}
        </div>
        <div className="dock-row"><DiceHUD faces={dice.faces} roll={dice.roll} total={state.last_roll} />
        <div className="dock-buttons">
          {ordinaryActions && <button className="game-button dock-action primary-action" disabled={!canRoll || blocked}
            onClick={() => request.submit({ type: "roll" })}><GameIcon name="roll" /><span>Roll</span></button>}
          {!state.game_over && <BoardControls state={state} resources={res} interaction={{ ...interaction,
            onSelectAction: action => { setTradeDraft(null); setDrawer(null); interaction.onSelectAction(action); },
            selection: { ...interaction.selection, waiting: interaction.selection.waiting || blocked } }} />}
          {ordinaryActions && <>
            <ActionButton action="dev" label="Dev Card" resources={res} disabled={blocked || !!purchaseReason}
              reason={purchaseReason} onClick={() => request.submit({ type: "buy_dev" })} />
            <button className="game-button dock-action end-action" disabled={!canEnd || blocked}
              onClick={() => request.submit({ type: "end_turn" })}><GameIcon name="end" /><span>End Turn</span></button>
          </>}
        </div>
        </div>
      </section>
    </footer>

    {(drawer === "log" || drawer === "info") && !mandatoryChoice && !state.game_over && <GameOverlay key={drawer} id={`game-${drawer}`}
      title={drawer === "log" ? "Event log" : "Game info"} onClose={closeDrawer}>
      {drawer === "log" ? <><pre className="game-log">{log.length ? log.join("\n") : "No events yet."}</pre>
        <BankSummary available={state.bank_available} /></> : <>
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
