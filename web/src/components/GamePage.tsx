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
  const canEnd = state.turn === youPid && pending === "none" && !!state.rolled;

  const handleDiscard = () => {
    client.sendCmd({ type: "discard", discards: discard });
  };

  const handleGold = () => {
    client.sendCmd({ type: "choose_gold", res: goldRes, qty: Number(goldQty) });
  };

  return (
    <div className="game-grid">
      <div className="board-wrap card">
        <BoardView
          state={state}
          youPid={youPid}
          selectedAction={selectedAction}
          onSendCmd={(cmd) => client.sendCmd(cmd)}
          onSelectAction={(a) => setSelectedAction(a)}
        />
      </div>

      <div className="game-sidebar">
        <div className="card panel">
          <div className="status-row">
            <div className="badge">Room: {match.room_code}</div>
            <div className="muted">Tick {match.tick}</div>
          </div>
          <div className="status-grid">
            <div>Turn: <strong>P{state.turn + 1}</strong></div>
            <div>Phase: <strong>{state.phase}</strong></div>
            <div>Pending: <strong>{pending}</strong>{pending === "robber_move" && pendingPid === youPid ? " (click map)" : ""}</div>
            <div>Status: <strong>{status}</strong></div>
            <div>Target VP: <strong>{targetVp}</strong></div>
            <div>Robbers: <strong>{robberCount}</strong></div>
          </div>
          <div className="muted">Seafarers: {seafarersEnabled ? "on" : "off"} | Pirate: {pirateEnabled ? "on" : "off"} | Gold: {goldEnabled ? "on" : "off"} | Move Ship: {moveShipEnabled ? "on" : "off"}</div>
          {mapId ? (
            <div className="muted">Map: {mapMeta.name || mapId} {mapMeta.description ? "- " + mapMeta.description : ""}</div>
          ) : null}
          {error ? <div className="error">Error: {error.message}</div> : null}
        </div>

        <div className="card panel">
          <h4>My Resources (P{youPid + 1})</h4>
          <div className="resource-grid">
            {resKeys.map((k) => (
              <div key={k} className={`res-chip res-${k}`}>
                <span>{k}</span>
                <strong>{res[k]}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="card panel">
          <h4>Actions</h4>
          <div className="row">
            <button onClick={() => client.sendCmd({ type: "roll" })} className="btn primary" disabled={!canRoll}>Roll</button>
            <button onClick={() => client.sendCmd({ type: "end_turn" })} className="btn" disabled={!canEnd}>End Turn</button>
          </div>
        </div>

        {needGold ? (
          <div className="card panel">
            <h4>Gold Choice: {goldNeed}</h4>
            <div className="row">
              <select value={goldRes} onChange={(e) => setGoldRes(e.target.value)}>
                {RESOURCES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <input type="number" min={1} max={goldNeed} value={goldQty} onChange={(e) => setGoldQty(Number(e.target.value))} />
              <button onClick={handleGold} className="btn primary">Choose</button>
            </div>
          </div>
        ) : null}

        {needDiscard ? (
          <div className="card panel">
            <h4>Discard Required: {required[String(youPid)]}</h4>
            {resKeys.map((k) => (
              <label key={k} className="field">
                <span>{k}</span>
                <input
                  type="number"
                  min={0}
                  max={res[k]}
                  value={discard[k] ?? 0}
                  onChange={(e) => setDiscard({ ...discard, [k]: Number(e.target.value) })}
                />
              </label>
            ))}
            <button onClick={handleDiscard} className="btn primary">Submit Discard</button>
          </div>
        ) : null}

        <div className="card panel">
          <h4>Players</h4>
          <ul>
            {players.map((p: any) => (
              <li key={p.pid}>
                P{p.pid + 1}: {p.name} (VP {p.vp})
              </li>
            ))}
          </ul>
        </div>

        <div className="card panel">
          <h4>Log</h4>
          <pre className="log-box">{log.join("\n")}</pre>
        </div>
      </div>
    </div>
  );
}
