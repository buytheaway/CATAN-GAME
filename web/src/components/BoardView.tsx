import { useMemo, useState } from "react";

const SQRT3 = 1.7320508075688772;

const TERRAIN_COLORS: Record<string, string> = {
  forest: "#1f7a3f",
  hills: "#d06016",
  pasture: "#7edc92",
  fields: "#f3c550",
  mountains: "#96a3b4",
  desert: "#d6c8a0",
  sea: "#0b4a6f",
  gold: "#eab308",
};

const PLAYER_COLORS = [
  "#ef4444",
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#a855f7",
  "#14b8a6",
];

type Edge = [number, number];

type BoardViewProps = {
  state: any;
  youPid: number;
  selectedAction: string | null;
  onSendCmd: (cmd: any) => void;
  onSelectAction: (action: string | null) => void;
};

function hexCorners(cx: number, cy: number, size: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 180) * (60 * i - 30);
    const x = cx + size * Math.cos(angle);
    const y = cy + size * Math.sin(angle);
    pts.push(`${x},${y}`);
  }
  return pts.join(" ");
}

const edgeKey = (a: number, b: number) => (a < b ? `${a},${b}` : `${b},${a}`);

export default function BoardView({ state, youPid, selectedAction, onSendCmd, onSelectAction }: BoardViewProps) {
  const tiles = state.tiles || [];
  const size = state.size || 58;
  const vertices: Record<string, [number, number]> = state.vertices || {};
  const edges: Edge[] = (state.edges || []) as Edge[];
  const occupiedE = state.occupied_e || {};
  const occupiedShips = state.occupied_ships || {};
  const occupiedV = state.occupied_v || {};
  const edgeAdj = state.edge_adj_hexes || {};
  const robberTile = state.robber_tile;
  const robbers: number[] = state.robbers && state.robbers.length ? state.robbers : [robberTile];
  const pirateTile = state.pirate_tile;
  const pending = state.pending_action || "none";
  const pendingPid = state.pending_pid;
  const setup = state.phase === "setup";
  const setupNeed = state.setup_need;
  const isYourTurn = state.turn === youPid;
  const enableSea = !!state.rules_config?.enable_seafarers;
  const enableMoveShip = !!state.rules_config?.enable_move_ship;
  const enablePirate = !!state.rules_config?.enable_pirate;
  const legal = state.legal || {};
  const hasLegal = legal && legal.pid === youPid;
  const legalSett = new Set<number>((hasLegal ? legal.settlements : []) || []);
  const legalRoad = new Set<string>(((hasLegal ? legal.roads : []) || []).map((e: number[]) => edgeKey(e[0], e[1])));
  const legalCity = new Set<number>((hasLegal ? legal.cities : []) || []);
  const legalShip = new Set<string>(((hasLegal ? legal.ships : []) || []).map((e: number[]) => edgeKey(e[0], e[1])));

  const [moveFrom, setMoveFrom] = useState<Edge | null>(null);

  const bounds = useMemo(() => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    tiles.forEach((t: any) => {
      const [cx, cy] = t.center || [0, 0];
      minX = Math.min(minX, cx - size);
      maxX = Math.max(maxX, cx + size);
      minY = Math.min(minY, cy - size);
      maxY = Math.max(maxY, cy + size);
    });
    const margin = size * 1.6;
    return {
      minX: minX - margin,
      minY: minY - margin,
      width: maxX - minX + margin * 2,
      height: maxY - minY + margin * 2,
    };
  }, [tiles, size]);

  const canPlaceSettlement = (vid: number) => {
    if (!isYourTurn) return false;
    if (setup && setupNeed !== "settlement") return false;
    if (hasLegal) return legalSett.has(vid);
    return occupiedV[String(vid)] === undefined;
  };

  const canUpgradeCity = (vid: number) => {
    if (!isYourTurn || state.phase !== "main") return false;
    const occ = occupiedV[String(vid)];
    if (hasLegal) return legalCity.has(vid);
    return Array.isArray(occ) && occ[0] === youPid && occ[1] === 1;
  };

  const canPlaceRoad = (a: number, b: number) => {
    if (!isYourTurn) return false;
    if (setup && setupNeed !== "road") return false;
    if (hasLegal) return legalRoad.has(edgeKey(a, b));
    return occupiedE[edgeKey(a, b)] === undefined;
  };

  const canPlaceShip = (a: number, b: number) => {
    if (!isYourTurn || !state.rules_config?.enable_seafarers) return false;
    const key = edgeKey(a, b);
    if (hasLegal) return legalShip.has(key);
    if (occupiedE[key] !== undefined || occupiedShips[key] !== undefined) return false;
    const adj = edgeAdj[key] || [];
    return adj.some((ti: number) => tiles[ti]?.terrain === "sea");
  };

  const handleVertexClick = (vid: number) => {
    if (selectedAction === "settlement" && canPlaceSettlement(vid)) {
      onSendCmd({ type: "place_settlement", vid, setup });
    }
    if (selectedAction === "city" && canUpgradeCity(vid)) {
      onSendCmd({ type: "upgrade_city", vid });
    }
  };

  const handleEdgeClick = (a: number, b: number) => {
    if (selectedAction === "road" && canPlaceRoad(a, b)) {
      onSendCmd({ type: "place_road", eid: [a, b], setup });
      return;
    }
    if (selectedAction === "ship" && canPlaceShip(a, b)) {
      onSendCmd({ type: "build_ship", eid: [a, b] });
      return;
    }
    if (selectedAction === "move_ship") {
      const key = edgeKey(a, b);
      if (!moveFrom) {
        if (occupiedShips[key] === youPid) {
          setMoveFrom([a, b]);
        }
        return;
      }
      onSendCmd({ type: "move_ship", from_eid: moveFrom, to_eid: [a, b] });
      setMoveFrom(null);
    }
  };

  const handleTileClick = (ti: number) => {
    if (pending === "robber_move" && pendingPid === youPid) {
      if (ti !== robberTile) onSendCmd({ type: "move_robber", tile: ti });
      return;
    }
    if (selectedAction === "pirate" && isYourTurn) {
      onSendCmd({ type: "move_pirate", tile: ti });
    }
  };

  return (
    <div style={{ width: "100%", background: "#081a24", borderRadius: 12, padding: 8 }}>
      <div style={{ color: "#bcd", fontSize: 12, marginBottom: 6 }}>
        Action: {selectedAction || "none"}
        {moveFrom ? ` (move from ${moveFrom[0]}-${moveFrom[1]})` : ""}
        {pending === "robber_move" && pendingPid === youPid ? " | Click a hex to move robber" : ""}
      </div>
      <svg
        viewBox={`${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`}
        width="100%"
        height="520"
        style={{ display: "block", background: "#0b2a3a", borderRadius: 12 }}
      >
        <defs>
          <filter id="tileShadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="2" dy="2" stdDeviation="2" floodColor="#03131c" floodOpacity="0.6" />
          </filter>
          <filter id="tokenShadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="1" dy="1" stdDeviation="1.5" floodColor="#000" floodOpacity="0.4" />
          </filter>
        </defs>
        {tiles.map((t: any, idx: number) => {
          const [cx, cy] = t.center || [0, 0];
          const fill = TERRAIN_COLORS[t.terrain] || "#64748b";
          return (
            <g key={`tile-${idx}`}>
              <polygon
                points={hexCorners(cx, cy, size)}
                fill={fill}
                stroke="#0b2230"
                strokeWidth={2}
                filter="url(#tileShadow)"
              />
              {t.number ? (
                <g>
                  <circle cx={cx} cy={cy} r={size * 0.28} fill="#f8fafc" stroke="#0b1220" strokeWidth={2} filter="url(#tokenShadow)" />
                  <text x={cx} y={cy + 4} textAnchor="middle" fontSize={14} fontWeight={700} fill={t.number === 6 || t.number === 8 ? "#ef4444" : "#0b1220"}>
                    {t.number}
                  </text>
                </g>
              ) : null}
              <polygon
                points={hexCorners(cx, cy, size)}
                fill="transparent"
                stroke="transparent"
                onClick={() => handleTileClick(idx)}
                style={{ cursor: pending === "robber_move" || selectedAction === "pirate" ? "pointer" : "default" }}
              />
            </g>
          );
        })}

        {edges.map(([a, b]) => {
          const pa = vertices[String(a)];
          const pb = vertices[String(b)];
          if (!pa || !pb) return null;
          const key = edgeKey(a, b);
          const owner = occupiedE[key];
          const shipOwner = occupiedShips[key];
          if (owner !== undefined) {
            return (
              <line
                key={`road-${key}`}
                x1={pa[0]}
                y1={pa[1]}
                x2={pb[0]}
                y2={pb[1]}
                stroke={PLAYER_COLORS[owner] || "#fff"}
                strokeWidth={10}
                strokeLinecap="round"
              />
            );
          }
          if (shipOwner !== undefined) {
            return (
              <line
                key={`ship-${key}`}
                x1={pa[0]}
                y1={pa[1]}
                x2={pb[0]}
                y2={pb[1]}
                stroke={PLAYER_COLORS[shipOwner] || "#fff"}
                strokeWidth={8}
                strokeDasharray="6 4"
                strokeLinecap="round"
              />
            );
          }
          return null;
        })}

        {Object.entries(occupiedV).map(([vid, occ]) => {
          const v = vertices[vid];
          if (!v || !Array.isArray(occ)) return null;
          const [pid, level] = occ as [number, number];
          const color = PLAYER_COLORS[pid] || "#fff";
          const x = v[0];
          const y = v[1];
          if (level === 1) {
            return (
              <g key={`sett-${vid}`}>
                <polygon points={`${x - 6},${y + 4} ${x},${y - 6} ${x + 6},${y + 4}`} fill={color} stroke="#0b1220" strokeWidth={1} />
                <rect x={x - 6} y={y + 4} width={12} height={8} fill={color} stroke="#0b1220" strokeWidth={1} />
              </g>
            );
          }
          return (
            <g key={`city-${vid}`}>
              <rect x={x - 8} y={y - 2} width={16} height={12} fill={color} stroke="#0b1220" strokeWidth={1} />
              <rect x={x - 5} y={y - 10} width={10} height={8} fill={color} stroke="#0b1220" strokeWidth={1} />
            </g>
          );
        })}

        {robbers.map((ti: number, idx: number) => {
          const t = tiles[ti];
          if (!t) return null;
          const [cx, cy] = t.center || [0, 0];
          return (
            <g key={`rob-${idx}`}>
              <circle cx={cx} cy={cy} r={size * 0.18} fill="#111" stroke="#e5e7eb" strokeWidth={2} />
              <text x={cx} y={cy + 4} textAnchor="middle" fontSize={12} fontWeight={700} fill="#e5e7eb">R</text>
            </g>
          );
        })}

        {pirateTile !== null && pirateTile !== undefined ? (() => {
          const t = tiles[pirateTile];
          if (!t) return null;
          const [cx, cy] = t.center || [0, 0];
          return (
            <g>
              <circle cx={cx} cy={cy} r={size * 0.16} fill="#0b2230" stroke="#22d3ee" strokeWidth={2} />
              <text x={cx} y={cy + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill="#d7eefc">P</text>
            </g>
          );
        })() : null}

        {edges.map(([a, b]) => {
          const pa = vertices[String(a)];
          const pb = vertices[String(b)];
          if (!pa || !pb) return null;
          const key = edgeKey(a, b);
          const occupied = occupiedE[key] !== undefined || occupiedShips[key] !== undefined;
          const showRoad = selectedAction === "road" && canPlaceRoad(a, b);
          const showShip = selectedAction === "ship" && canPlaceShip(a, b);
          const showMoveFrom = selectedAction === "move_ship" && moveFrom === null && occupiedShips[key] === youPid;
          const showMoveTo = selectedAction === "move_ship" && moveFrom !== null && !occupied &&
            (a === moveFrom[0] || a === moveFrom[1] || b === moveFrom[0] || b === moveFrom[1]);
          if (!showRoad && !showShip && !showMoveFrom && !showMoveTo) return null;
          return (
            <line
              key={`edge-hit-${key}`}
              x1={pa[0]}
              y1={pa[1]}
              x2={pb[0]}
              y2={pb[1]}
              stroke={showMoveFrom ? "#f59e0b" : (showShip || showMoveTo ? "#60a5fa" : "#22c55e")}
              strokeOpacity={0.6}
              strokeWidth={14}
              strokeLinecap="round"
              onClick={() => handleEdgeClick(a, b)}
              style={{ cursor: "pointer" }}
            />
          );
        })}

        {Object.entries(vertices).map(([vid, v]) => {
          const [x, y] = v;
          const showSettlement = selectedAction === "settlement" && canPlaceSettlement(Number(vid));
          const showCity = selectedAction === "city" && canUpgradeCity(Number(vid));
          if (!showSettlement && !showCity) return null;
          return (
            <circle
              key={`v-hit-${vid}`}
              cx={x}
              cy={y}
              r={7}
              fill={showCity ? "#f59e0b" : "#22c55e"}
              fillOpacity={0.7}
              stroke="#0b1220"
              strokeWidth={1}
              onClick={() => handleVertexClick(Number(vid))}
              style={{ cursor: "pointer" }}
            />
          );
        })}

        {(state.ports || []).map((p: any, idx: number) => {
          const [[a, b], kind] = p;
          const pa = vertices[String(a)];
          const pb = vertices[String(b)];
          if (!pa || !pb) return null;
          const cx = (pa[0] + pb[0]) / 2;
          const cy = (pa[1] + pb[1]) / 2;
          const ratio = String(kind).includes("3:1") ? "3:1" : "2:1";
          return (
            <g key={`port-${idx}`}>
              <circle cx={cx} cy={cy} r={size * 0.18} fill="#0b2433" stroke="#22d3ee" strokeWidth={1.5} />
              <text x={cx} y={cy + 3} textAnchor="middle" fontSize={10} fontWeight={700} fill="#d7eefc">{ratio}</text>
            </g>
          );
        })}
      </svg>

      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        {([
          ["settlement", "Settlement"],
          ["road", "Road"],
          ["city", "City"],
          enableSea ? ["ship", "Ship"] : null,
          enableSea && enableMoveShip ? ["move_ship", "Move Ship"] : null,
          enablePirate ? ["pirate", "Pirate"] : null,
        ] as Array<[string, string] | null>)
          .filter((x): x is [string, string] => Boolean(x))
          .map(([key, label]) => (
            <button
              key={key}
              onClick={() => onSelectAction(selectedAction === key ? null : key)}
              style={{
              padding: "6px 10px",
              borderRadius: 8,
              border: "1px solid #193042",
              background: selectedAction === key ? "#123549" : "#0b2433",
              color: "#d7eefc",
              fontWeight: 600,
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
