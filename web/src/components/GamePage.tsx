import { useMemo, useState } from "react";
import { MatchState, RoomState, ServerError, WSClient } from "../wsClient";

const RESOURCES = ["wood", "brick", "sheep", "wheat", "ore"];

type Edge = [number, number];

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

  const [robberTile, setRobberTile] = useState(0);
  const [discard, setDiscard] = useState<Record<string, number>>({});
  const [shipA, setShipA] = useState(0);
  const [shipB, setShipB] = useState(0);
  const [moveFromA, setMoveFromA] = useState(0);
  const [moveFromB, setMoveFromB] = useState(0);
  const [moveToA, setMoveToA] = useState(0);
  const [moveToB, setMoveToB] = useState(0);
  const [pirateTile, setPirateTile] = useState(0);
  const [pirateVictim, setPirateVictim] = useState(0);
  const [goldRes, setGoldRes] = useState(RESOURCES[0]);
  const [goldQty, setGoldQty] = useState(1);

  const resKeys = useMemo(() => Object.keys(res), [res]);

  const canRoll = state.turn === youPid && state.phase === "main" && !state.rolled && pending === "none";
  const canEnd = state.turn === youPid && pending === "none";

  const edges: Edge[] = (state.edges || []) as Edge[];
  const edgeAdj = state.edge_adj_hexes || {};
  const tiles = state.tiles || [];
  const occupiedE = state.occupied_e || {};
  const occupiedShips = state.occupied_ships || {};
  const occupiedV = state.occupied_v || {};
  const pirateBlockTile = state.pirate_tile ?? null;

  const legalShipEdges = useMemo(() => {
    if (!seafarersEnabled) return [] as Edge[];
    const ownedVertices = new Set<number>();
    Object.entries(occupiedV).forEach(([vid, occ]) => {
      if (Array.isArray(occ) && occ[0] === youPid) ownedVertices.add(Number(vid));
    });
    const ownedEdges = new Set<string>();
    Object.entries(occupiedE).forEach(([k, pid]) => {
      if (pid === youPid) ownedEdges.add(k);
    });
    Object.entries(occupiedShips).forEach(([k, pid]) => {
      if (pid === youPid) ownedEdges.add(k);
    });
    const edgeKey = (a: number, b: number) => (a < b ? `${a},${b}` : `${b},${a}`);
    const hasSea = (a: number, b: number) => {
      const key = edgeKey(a, b);
      const adj = edgeAdj[key] || [];
      return adj.some((ti: number) => tiles[ti]?.terrain === "sea");
    };
    const blockedByPirate = (a: number, b: number) => {
      if (pirateBlockTile === null || pirateBlockTile === undefined) return false;
      const key = edgeKey(a, b);
      const adj = edgeAdj[key] || [];
      return adj.includes(pirateBlockTile);
    };
    const connectedToNetwork = (a: number, b: number) => {
      if (ownedVertices.has(a) || ownedVertices.has(b)) return true;
      for (const k of ownedEdges) {
        const [ea, eb] = k.split(",").map((x) => Number(x));
        if (ea === a || ea === b || eb === a || eb === b) return true;
      }
      return false;
    };
    const out: Edge[] = [];
    for (const [a, b] of edges) {
      const key = edgeKey(a, b);
      if (occupiedE[key] !== undefined || occupiedShips[key] !== undefined) continue;
      if (!hasSea(a, b)) continue;
      if (pirateEnabled && blockedByPirate(a, b)) continue;
      if (!connectedToNetwork(a, b)) continue;
      out.push([a, b]);
    }
    return out;
  }, [edges, edgeAdj, tiles, occupiedE, occupiedShips, occupiedV, youPid, seafarersEnabled, pirateEnabled, pirateBlockTile]);

  const handleDiscard = () => {
    client.sendCmd({ type: "discard", discards: discard });
  };

  const handleRobber = () => {
    client.sendCmd({ type: "move_robber", tile: Number(robberTile) });
  };

  const handleBuildShip = () => {
    client.sendCmd({ type: "build_ship", eid: [Number(shipA), Number(shipB)] });
  };

  const handleMoveShip = () => {
    client.sendCmd({ type: "move_ship", from_eid: [Number(moveFromA), Number(moveFromB)], to_eid: [Number(moveToA), Number(moveToB)] });
  };

  const handlePirate = () => {
    client.sendCmd({ type: "move_pirate", tile: Number(pirateTile), victim: Number(pirateVictim) });
  };

  const handleGold = () => {
    client.sendCmd({ type: "choose_gold", res: goldRes, qty: Number(goldQty) });
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
        <div>Target VP: {targetVp}</div>
        <div>Robbers: {robberCount}</div>
        <div>Seafarers: {seafarersEnabled ? "on" : "off"}</div>
        <div>Pirate: {pirateEnabled ? "on" : "off"}</div>
        <div>Gold: {goldEnabled ? "on" : "off"}</div>
        <div>Move Ship: {moveShipEnabled ? "on" : "off"}</div>
        {mapId ? (
          <div>Map: {mapMeta.name || mapId} {mapMeta.description ? `— ${mapMeta.description}` : ""}</div>
        ) : null}
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

      {seafarersEnabled ? (
        <div style={{ border: "1px solid #ddd", padding: 12 }}>
          <h4>Build Ship (edge)</h4>
          {legalShipEdges.length ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <select onChange={(e) => {
                const [a, b] = e.target.value.split(",").map(Number);
                setShipA(a); setShipB(b);
              }}>
                {legalShipEdges.map(([a, b]) => (
                  <option key={`${a},${b}`} value={`${a},${b}`}>{a}-{b}</option>
                ))}
              </select>
              <button onClick={handleBuildShip}>Build Ship</button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span>Vertex A</span>
              <input type="number" value={shipA} onChange={(e) => setShipA(Number(e.target.value))} />
              <span>Vertex B</span>
              <input type="number" value={shipB} onChange={(e) => setShipB(Number(e.target.value))} />
              <button onClick={handleBuildShip}>Build Ship</button>
            </div>
          )}
          <div style={{ fontSize: 12, opacity: 0.7 }}>Ship cost: wood + sheep</div>
        </div>
      ) : null}

      {moveShipEnabled ? (
        <div style={{ border: "1px solid #ddd", padding: 12 }}>
          <h4>Move Ship</h4>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span>From A</span>
            <input type="number" value={moveFromA} onChange={(e) => setMoveFromA(Number(e.target.value))} />
            <span>From B</span>
            <input type="number" value={moveFromB} onChange={(e) => setMoveFromB(Number(e.target.value))} />
            <span>To A</span>
            <input type="number" value={moveToA} onChange={(e) => setMoveToA(Number(e.target.value))} />
            <span>To B</span>
            <input type="number" value={moveToB} onChange={(e) => setMoveToB(Number(e.target.value))} />
            <button onClick={handleMoveShip}>Move</button>
          </div>
        </div>
      ) : null}

      {pirateEnabled ? (
        <div style={{ border: "1px solid #ddd", padding: 12 }}>
          <h4>Move Pirate</h4>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span>Tile</span>
            <input type="number" value={pirateTile} onChange={(e) => setPirateTile(Number(e.target.value))} />
            <span>Victim pid</span>
            <input type="number" value={pirateVictim} onChange={(e) => setPirateVictim(Number(e.target.value))} />
            <button onClick={handlePirate}>Move</button>
          </div>
        </div>
      ) : null}

      {needGold ? (
        <div style={{ border: "1px solid #ddd", padding: 12 }}>
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
