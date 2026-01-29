import { useMemo, useState } from "react";
import { MatchState, RoomState, ServerError, WSClient } from "../wsClient";

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

  const [robberTile, setRobberTile] = useState(0);
  const [discard, setDiscard] = useState<Record<string, number>>({});

  const resKeys = useMemo(() => Object.keys(res), [res]);

  const canRoll = state.turn === youPid && state.phase === "main" && !state.rolled && pending === "none";
  const canEnd = state.turn === youPid && pending === "none";

  const handleDiscard = () => {
    client.sendCmd({ type: "discard", discards: discard });
  };

  const handleRobber = () => {
    client.sendCmd({ type: "move_robber", tile: Number(robberTile) });
  };

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div>
        <div>Status: {status}</div>
        <div>Room: {match.room_code}</div>
        <div>Tick: {match.tick}</div>
        <div>Turn: P{state.turn + 1}</div>
        <div>Phase: {state.phase}</div>
        <div>Pending: {pending}</div>
        {error ? <div style={{ color: "crimson" }}>Error: {error.message}</div> : null}
      </div>

      <div>
        <h4>My Resources (P{youPid + 1})</h4>
        <ul>
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

      {needDiscard ? (
        <div style={{ border: "1px solid #ddd", padding: 12 }}>
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

      {pending === "robber_move" && pendingPid === youPid ? (
        <div style={{ border: "1px solid #ddd", padding: 12 }}>
          <h4>Move Robber</h4>
          <div>
            Tile index: <input type="number" value={robberTile} onChange={(e) => setRobberTile(Number(e.target.value))} />
          </div>
          <button onClick={handleRobber}>Move</button>
        </div>
      ) : null}

      <div>
        <h4>Players</h4>
        <ul>
          {players.map((p: any) => (
            <li key={p.pid}>
              P{p.pid + 1}: {p.name} (VP {p.vp})
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h4>Log</h4>
        <pre style={{ maxHeight: 240, overflow: "auto", background: "#f8f8f8", padding: 8 }}>
          {log.join("\n")}
        </pre>
      </div>
    </div>
  );
}
