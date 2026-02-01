import { useMemo, useState } from "react";
import { MatchState, RoomState, ServerError, WSClient } from "../wsClient";
import BoardView from "./BoardView";

const RESOURCES = ["wood", "brick", "sheep", "wheat", "ore"];

export default function GamePage({
  client,
  match,
  room,
  status,
  log,
  error,
}: {
  client: WSClient;
  match: MatchState;
  room: RoomState | null;
  status: string;
  log: string[];
  error: ServerError | null;
}) {
  const state = match.state || {};
  const youPid = client.youPid ?? 0;
  const players = state.players || [];
  const me = players[youPid] || { res: {} };
  const res = me.res || {};
  const pending = state.pending_action || "none";
  const pendingPid = state.pending_pid;
  const required = state.discard_required || {};
  const needDiscard = pending === "discard" && required[String(youPid)] > 0;
  const pendingGold = state.pending_gold || {};
  const needGold = pending === "choose_gold" && pendingGold[String(youPid)] > 0;
  const goldNeed = Number(pendingGold[String(youPid)] || 0);
  const mapMeta = state.map_meta || room?.map_meta || {};
  const mapId = state.map_id || room?.map_id || "";
  const rules = state.rules_config || {};
  const targetVp = rules.target_vp ?? 10;
  const robberCount = rules.robber_count ?? (state.robbers ? state.robbers.length : 1);
  const seafarersEnabled = !!rules.enable_seafarers;
  const pirateEnabled = !!rules.enable_pirate;
  const goldEnabled = !!rules.enable_gold;
  const moveShipEnabled = !!rules.enable_move_ship;

  const [discard, setDiscard] = useState<Record<string, number>>({});
  const [goldRes, setGoldRes] = useState(RESOURCES[0]);
  const [goldQty, setGoldQty] = useState(1);
  const [selectedAction, setSelectedAction] = useState<string | null>(null);

  const resKeys = useMemo(() => Object.keys(res), [res]);

  const canRoll = state.turn === youPid && state.phase === "main" && !state.rolled && pending === "none";
  const canEnd = state.turn === youPid && pending === "none";

  const handleDiscard = () => {
    client.sendCmd({ type: "discard", discards: discard });
  };

  const handleGold = () => {
    client.sendCmd({ type: "choose_gold", res: goldRes, qty: Number(goldQty) });
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(260px, 1fr)", gap: 12 }}>
      <BoardView
        state={state}
        youPid={youPid}
        selectedAction={selectedAction}
        onSendCmd={(cmd) => client.sendCmd(cmd)}
        onSelectAction={(a) => setSelectedAction(a)}
      />

      <div style={{ display: "grid", gap: 12 }}>
        <div style={{ background: "#0b2230", border: "1px solid #173245", borderRadius: 12, padding: 12, color: "#d7eefc" }}>
          <div>Status: {status}</div>
          <div>Room: {match.room_code}</div>
          <div>Tick: {match.tick}</div>
          <div>Turn: P{state.turn + 1}</div>
          <div>Phase: {state.phase}</div>
          <div>Pending: {pending}{pending === "robber_move" && pendingPid === youPid ? " (click map)" : ""}</div>
          <div>Target VP: {targetVp}</div>
          <div>Robbers: {robberCount}</div>
          <div>Seafarers: {seafarersEnabled ? "on" : "off"}</div>
          <div>Pirate: {pirateEnabled ? "on" : "off"}</div>
          <div>Gold: {goldEnabled ? "on" : "off"}</div>
          <div>Move Ship: {moveShipEnabled ? "on" : "off"}</div>
          {mapId ? (
            <div>Map: {mapMeta.name || mapId} {mapMeta.description ? `— ${mapMeta.description}` : ""}</div>
          ) : null}
          {error ? <div style={{ color: "#f87171" }}>Error: {error.message}</div> : null}
        </div>

        <div style={{ background: "#0b2230", border: "1px solid #173245", borderRadius: 12, padding: 12, color: "#d7eefc" }}>
          <h4 style={{ margin: "0 0 8px 0" }}>My Resources (P{youPid + 1})</h4>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {resKeys.map((k) => (
              <li key={k}>
                {k}: {res[k]}
              </li>
            ))}
          </ul>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => client.sendCmd({ type: "roll" })} disabled={!canRoll}>Roll</button>
          <button onClick={() => client.sendCmd({ type: "end_turn" })} disabled={!canEnd}>End Turn</button>
        </div>

        {needGold ? (
          <div style={{ border: "1px solid #173245", background: "#0b2230", padding: 12, borderRadius: 12, color: "#d7eefc" }}>
            <h4>Gold Choice: {goldNeed}</h4>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <select value={goldRes} onChange={(e) => setGoldRes(e.target.value)}>
                {RESOURCES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <input type="number" min={1} max={goldNeed} value={goldQty} onChange={(e) => setGoldQty(Number(e.target.value))} />
              <button onClick={handleGold}>Choose</button>
            </div>
          </div>
        ) : null}

        {needDiscard ? (
          <div style={{ border: "1px solid #173245", background: "#0b2230", padding: 12, borderRadius: 12, color: "#d7eefc" }}>
            <h4>Discard Required: {required[String(youPid)]}</h4>
            {resKeys.map((k) => (
              <div key={k}>
                {k}: <input
                  type="number"
                  min={0}
                  max={res[k]}
                  value={discard[k] ?? 0}
                  onChange={(e) => setDiscard({ ...discard, [k]: Number(e.target.value) })}
                />
              </div>
            ))}
            <button onClick={handleDiscard}>Submit Discard</button>
          </div>
        ) : null}

        <div style={{ background: "#0b2230", border: "1px solid #173245", borderRadius: 12, padding: 12, color: "#d7eefc" }}>
          <h4 style={{ margin: "0 0 8px 0" }}>Players</h4>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {players.map((p: any) => (
              <li key={p.pid}>
                P{p.pid + 1}: {p.name} (VP {p.vp})
              </li>
            ))}
          </ul>
        </div>

        <div style={{ background: "#0b2230", border: "1px solid #173245", borderRadius: 12, padding: 12, color: "#d7eefc" }}>
          <h4 style={{ margin: "0 0 8px 0" }}>Log</h4>
          <pre style={{ maxHeight: 240, overflow: "auto", background: "#061a25", padding: 8, borderRadius: 8 }}>
            {log.join("\n")}
          </pre>
        </div>
      </div>
    </div>
  );
}
