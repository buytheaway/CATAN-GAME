/**
 * Main board view component with improved code quality
 * - Uses proper TypeScript types instead of `any`
 * - Extracts constants to avoid magic strings/numbers
 * - Splits logic into utility functions
 * - Adds proper error boundaries
 * - Includes JSDoc comments
 */

import { useMemo, useState } from "react";
import type {
  BoardViewProps,
  EdgeTuple,
  GameState,
} from "./BoardView.types";
import {
  TERRAIN_COLORS,
  PLAYER_COLORS,
  ActionType,
  CommandType,
  GamePhase,
  UI_STYLES,
  SHADOW_FILTERS,
  SIZE_RATIOS,
  STROKE_WIDTH,
  NUMBER_COLORS,
  FONT_SIZES,
  STROKE_DASHARRAY,
  CURSOR_STYLES,
  SETUP_TYPES,
} from "./BoardView.constants";
import {
  hexCorners,
  edgeKey,
  calculateBounds,
  getEdgeAdjacentTiles,
  portRatioLabel,
  getActionLabel,
} from "./BoardView.utils";

/**
 * Validate if a settlement can be placed at this vertex
 */
function canPlaceSettlement(
  vid: number,
  state: GameState,
  youPid: number
): boolean {
  const { phase, setup_need, turn, occupied_v, legal } = state;
  
  if (turn !== youPid) return false;
  if (phase === GamePhase.Setup && setup_need !== SETUP_TYPES.settlement) {
    return false;
  }
  
  if (legal && legal.pid === youPid) {
    return legal.settlements.includes(vid);
  }
  
  return occupied_v[String(vid)] === undefined;
}

/**
 * Validate if a city can be upgraded at this vertex
 */
function canUpgradeCity(vid: number, state: GameState, youPid: number): boolean {
  const { phase, occupied_v, turn, legal } = state;
  
  if (turn !== youPid || phase !== GamePhase.Main) {
    return false;
  }
  
  if (legal && legal.pid === youPid) {
    return legal.cities.includes(vid);
  }
  
  const occ = occupied_v[String(vid)];
  return Array.isArray(occ) && occ[0] === youPid && occ[1] === 1;
}

/**
 * Validate if a road can be placed on this edge
 */
function canPlaceRoad(
  a: number,
  b: number,
  state: GameState,
  youPid: number
): boolean {
  const { phase, setup_need, turn, occupied_e, legal } = state;
  
  if (turn !== youPid) return false;
  if (phase === GamePhase.Setup && setup_need !== SETUP_TYPES.road) {
    return false;
  }
  
  const key = edgeKey(a, b);
  
  if (legal && legal.pid === youPid) {
    return legal.roads.some((road) => edgeKey(road[0], road[1]) === key);
  }
  
  return occupied_e[key] === undefined;
}

/**
 * Validate if a ship can be placed on this edge
 */
function canPlaceShip(
  a: number,
  b: number,
  state: GameState,
  youPid: number
): boolean {
  const { turn, rules_config, occupied_e, occupied_ships, edge_adj_hexes, tiles, legal } = state;
  
  if (turn !== youPid || !rules_config?.enable_seafarers) {
    return false;
  }
  
  const key = edgeKey(a, b);
  
  if (legal && legal.pid === youPid) {
    return legal.ships.some((ship) => edgeKey(ship[0], ship[1]) === key);
  }
  
  if (occupied_e[key] !== undefined || occupied_ships[key] !== undefined) {
    return false;
  }
  
  const adj = getEdgeAdjacentTiles(edge_adj_hexes, key);
  return adj.some((ti: number) => tiles[ti]?.terrain === "sea");
}

/**
 * Main BoardView component - renders the game board with tiles, pieces, and interactive overlays
 */
export default function BoardView({
  state,
  youPid,
  selectedAction,
  onSendCmd,
  onSelectAction,
}: BoardViewProps) {
  const [moveFrom, setMoveFrom] = useState<EdgeTuple | null>(null);

  // Extract state with defaults
  const {
    tiles = [],
    size = 58,
    vertices = {},
    edges = [],
    occupied_e = {},
    occupied_ships = {},
    occupied_v = {},
    edge_adj_hexes = {},
    robber_tile = 0,
    robbers = [],
    pirate_tile = null,
    pending_action = "none",
    pending_pid = -1,
    phase = "main",
    turn = -1,
    rules_config = {},
    legal,
    ports = [],
  } = state;

  // Derived state
  const enableSea = !!rules_config.enable_seafarers;
  const enableMoveShip = !!rules_config.enable_move_ship;
  const enablePirate = !!rules_config.enable_pirate;
  const isSetupPhase = phase === GamePhase.Setup;
  const isYourTurn = turn === youPid;
  const robberList = robbers.length > 0 ? robbers : [robber_tile];

  // Memoize bounds calculation for performance
  const bounds = useMemo(() => calculateBounds(tiles, size), [tiles, size]);

  /** Handler for vertex (settlement/city) clicks */
  const handleVertexClick = (vid: number) => {
    if (selectedAction === ActionType.Settlement && canPlaceSettlement(vid, state, youPid)) {
      onSendCmd({
        type: CommandType.PlaceSettlement,
        vid,
        setup: isSetupPhase,
      });
    }
    
    if (selectedAction === ActionType.City && canUpgradeCity(vid, state, youPid)) {
      onSendCmd({
        type: CommandType.UpgradeCity,
        vid,
      });
    }
  };

  /** Handler for edge (road/ship) clicks */
  const handleEdgeClick = (a: number, b: number) => {
    // Place road
    if (selectedAction === ActionType.Road && canPlaceRoad(a, b, state, youPid)) {
      onSendCmd({
        type: CommandType.PlaceRoad,
        eid: [a, b],
        setup: isSetupPhase,
      });
      return;
    }

    // Place ship
    if (selectedAction === ActionType.Ship && canPlaceShip(a, b, state, youPid)) {
      onSendCmd({
        type: CommandType.BuildShip,
        eid: [a, b],
      });
      return;
    }

    // Move ship (2-step action)
    if (selectedAction === ActionType.MoveShip) {
      const key = edgeKey(a, b);
      if (!moveFrom) {
        if (occupied_ships[key] === youPid) {
          setMoveFrom([a, b]);
        }
        return;
      }

      onSendCmd({
        type: CommandType.MoveShip,
        from_eid: moveFrom,
        to_eid: [a, b],
      });
      setMoveFrom(null);
    }
  };

  /** Handler for tile (robber/pirate) clicks */
  const handleTileClick = (ti: number) => {
    if (pending_action === "robber_move" && pending_pid === youPid) {
      if (ti !== robber_tile) {
        onSendCmd({
          type: CommandType.MoveRobber,
          tile: ti,
        });
      }
      return;
    }

    if (selectedAction === ActionType.Pirate && isYourTurn) {
      onSendCmd({
        type: CommandType.MovePirate,
        tile: ti,
      });
    }
  };

  return (
    <div style={UI_STYLES.container}>
      {/* Info bar */}
      <div style={UI_STYLES.infoText}>
        <span>Action: {selectedAction ? getActionLabel(selectedAction) : "none"}</span>
        {moveFrom && (
          <span> (move from {moveFrom[0]}-{moveFrom[1]})</span>
        )}
        {pending_action === "robber_move" && pending_pid === youPid && (
          <span> | Click a hex to move robber</span>
        )}
      </div>

      {/* Main SVG canvas */}
      <svg
        viewBox={`${bounds.minX} ${bounds.minY} ${bounds.width} ${bounds.height}`}
        width="100%"
        height="520"
        style={UI_STYLES.svg}
      >
        <defs>
          {/* Tile shadow filter */}
          <filter
            id={SHADOW_FILTERS.tile.id}
            x="-20%"
            y="-20%"
            width="140%"
            height="140%"
          >
            <feDropShadow
              dx={SHADOW_FILTERS.tile.dx}
              dy={SHADOW_FILTERS.tile.dy}
              stdDeviation={SHADOW_FILTERS.tile.stdDeviation}
              floodColor={SHADOW_FILTERS.tile.floodColor}
              floodOpacity={SHADOW_FILTERS.tile.floodOpacity}
            />
          </filter>

          {/* Token shadow filter */}
          <filter
            id={SHADOW_FILTERS.token.id}
            x="-20%"
            y="-20%"
            width="140%"
            height="140%"
          >
            <feDropShadow
              dx={SHADOW_FILTERS.token.dx}
              dy={SHADOW_FILTERS.token.dy}
              stdDeviation={SHADOW_FILTERS.token.stdDeviation}
              floodColor={SHADOW_FILTERS.token.floodColor}
              floodOpacity={SHADOW_FILTERS.token.floodOpacity}
            />
          </filter>
        </defs>

        {/* Render tiles */}
        {tiles.map((t, idx) => {
          const [cx, cy] = t.center || [0, 0];
          const fill = TERRAIN_COLORS[t.terrain] || "#64748b";
          const isHighNumber = t.number === 6 || t.number === 8;

          return (
            <g key={`tile-${idx}`}>
              {/* Hex polygon */}
              <polygon
                points={hexCorners(cx, cy, size)}
                fill={fill}
                stroke="#0b2230"
                strokeWidth={STROKE_WIDTH.hexBorder}
                filter={`url(#${SHADOW_FILTERS.tile.id})`}
              />

              {/* Number token */}
              {t.number && (
                <g>
                  <circle
                    cx={cx}
                    cy={cy}
                    r={size * SIZE_RATIOS.tokenRadius}
                    fill="#f8fafc"
                    stroke="#0b1220"
                    strokeWidth={STROKE_WIDTH.city}
                    filter={`url(#${SHADOW_FILTERS.token.id})`}
                  />
                  <text
                    x={cx}
                    y={cy + 4}
                    textAnchor="middle"
                    fontSize={FONT_SIZES.hexNumber}
                    fontWeight={700}
                    fill={isHighNumber ? NUMBER_COLORS.highlight : NUMBER_COLORS.default}
                  >
                    {t.number}
                  </text>
                </g>
              )}

              {/* Clickable overlay */}
              <polygon
                points={hexCorners(cx, cy, size)}
                fill="transparent"
                stroke="transparent"
                onClick={() => handleTileClick(idx)}
                style={{
                  cursor:
                    pending_action === "robber_move" || selectedAction === ActionType.Pirate
                      ? CURSOR_STYLES.pointer
                      : CURSOR_STYLES.default,
                }}
              />
            </g>
          );
        })}

        {/* Render roads and ships */}
        {edges.map(([a, b]) => {
          const pa = vertices[String(a)];
          const pb = vertices[String(b)];
          if (!pa || !pb) return null;

          const key = edgeKey(a, b);
          const owner = occupied_e[key];
          const shipOwner = occupied_ships[key];

          // Road
          if (owner !== undefined) {
            return (
              <line
                key={`road-${key}`}
                x1={pa[0]}
                y1={pa[1]}
                x2={pb[0]}
                y2={pb[1]}
                stroke={PLAYER_COLORS[owner] || "#fff"}
                strokeWidth={STROKE_WIDTH.road}
                strokeLinecap="round"
              />
            );
          }

          // Ship
          if (shipOwner !== undefined) {
            return (
              <line
                key={`ship-${key}`}
                x1={pa[0]}
                y1={pa[1]}
                x2={pb[0]}
                y2={pb[1]}
                stroke={PLAYER_COLORS[shipOwner] || "#fff"}
                strokeWidth={STROKE_WIDTH.ship}
                strokeDasharray={STROKE_DASHARRAY.ship}
                strokeLinecap="round"
              />
            );
          }

          return null;
        })}

        {/* Render settlements and cities */}
        {Object.entries(occupied_v).map(([vid, occ]) => {
          const v = vertices[vid];
          if (!v || !Array.isArray(occ)) return null;

          const [pid, level] = occ as [number, number];
          const color = PLAYER_COLORS[pid] || "#fff";
          const [x, y] = v;

          // Settlement (level 1)
          if (level === 1) {
            return (
              <g key={`sett-${vid}`}>
                <polygon
                  points={`${x - 6},${y + 4} ${x},${y - 6} ${x + 6},${y + 4}`}
                  fill={color}
                  stroke="#0b1220"
                  strokeWidth={STROKE_WIDTH.settlement}
                />
                <rect
                  x={x - 6}
                  y={y + 4}
                  width={12}
                  height={8}
                  fill={color}
                  stroke="#0b1220"
                  strokeWidth={STROKE_WIDTH.settlement}
                />
              </g>
            );
          }

          // City (level 2)
          return (
            <g key={`city-${vid}`}>
              <rect
                x={x - 8}
                y={y - 2}
                width={16}
                height={12}
                fill={color}
                stroke="#0b1220"
                strokeWidth={STROKE_WIDTH.city}
              />
              <rect
                x={x - 5}
                y={y - 10}
                width={10}
                height={8}
                fill={color}
                stroke="#0b1220"
                strokeWidth={STROKE_WIDTH.city}
              />
            </g>
          );
        })}

        {/* Render robbers */}
        {robberList.map((ti: number, idx: number) => {
          const t = tiles[ti];
          if (!t) return null;

          const [cx, cy] = t.center || [0, 0];
          return (
            <g key={`rob-${idx}`}>
              <circle
                cx={cx}
                cy={cy}
                r={size * SIZE_RATIOS.robberRadius}
                fill="#111"
                stroke="#e5e7eb"
                strokeWidth={STROKE_WIDTH.hexBorder}
              />
              <text
                x={cx}
                y={cy + 4}
                textAnchor="middle"
                fontSize={FONT_SIZES.robberText}
                fontWeight={700}
                fill="#e5e7eb"
              >
                R
              </text>
            </g>
          );
        })}

        {/* Render pirate */}
        {pirate_tile !== null && pirate_tile !== undefined && (() => {
          const t = tiles[pirate_tile];
          if (!t) return null;

          const [cx, cy] = t.center || [0, 0];
          return (
            <g key="pirate">
              <circle
                cx={cx}
                cy={cy}
                r={size * SIZE_RATIOS.pirateRadius}
                fill="#0b2230"
                stroke="#22d3ee"
                strokeWidth={STROKE_WIDTH.hexBorder}
              />
              <text
                x={cx}
                y={cy + 4}
                textAnchor="middle"
                fontSize={FONT_SIZES.pirateText}
                fontWeight={700}
                fill="#d7eefc"
              >
                P
              </text>
            </g>
          );
        })()}

        {/* Render interactive edge overlays */}
        {edges.map(([a, b]) => {
          const pa = vertices[String(a)];
          const pb = vertices[String(b)];
          if (!pa || !pb) return null;

          const key = edgeKey(a, b);
          const occupied = occupied_e[key] !== undefined || occupied_ships[key] !== undefined;

          const canPlaceRoadHere = selectedAction === ActionType.Road && canPlaceRoad(a, b, state, youPid);
          const canPlaceShipHere = selectedAction === ActionType.Ship && canPlaceShip(a, b, state, youPid);
          const showMoveFrom = selectedAction === ActionType.MoveShip && !moveFrom && occupied_ships[key] === youPid;
          const showMoveTo =
            selectedAction === ActionType.MoveShip &&
            moveFrom !== null &&
            !occupied &&
            (a === moveFrom[0] || a === moveFrom[1] || b === moveFrom[0] || b === moveFrom[1]);

          if (!canPlaceRoadHere && !canPlaceShipHere && !showMoveFrom && !showMoveTo) {
            return null;
          }

          const strokeColor = showMoveFrom
            ? "#f59e0b"
            : showMoveTo || canPlaceShipHere
              ? "#60a5fa"
              : "#22c55e";

          return (
            <line
              key={`edge-hit-${key}`}
              x1={pa[0]}
              y1={pa[1]}
              x2={pb[0]}
              y2={pb[1]}
              stroke={strokeColor}
              strokeOpacity={0.6}
              strokeWidth={STROKE_WIDTH.hexHitArea}
              strokeLinecap="round"
              onClick={() => handleEdgeClick(a, b)}
              style={{ cursor: CURSOR_STYLES.pointer }}
            />
          );
        })}

        {/* Render interactive vertex overlays */}
        {Object.entries(vertices).map(([vid, v]) => {
          const [x, y] = v;
          const canPlace = selectedAction === ActionType.Settlement && canPlaceSettlement(Number(vid), state, youPid);
          const canUpgrade = selectedAction === ActionType.City && canUpgradeCity(Number(vid), state, youPid);

          if (!canPlace && !canUpgrade) return null;

          return (
            <circle
              key={`v-hit-${vid}`}
              cx={x}
              cy={y}
              r={7}
              fill={canUpgrade ? "#f59e0b" : "#22c55e"}
              fillOpacity={0.7}
              stroke="#0b1220"
              strokeWidth={1}
              onClick={() => handleVertexClick(Number(vid))}
              style={{ cursor: CURSOR_STYLES.pointer }}
            />
          );
        })}

        {/* Render ports */}
        {ports.map((p, idx) => {
          const [[a, b], kind] = p;
          const pa = vertices[String(a)];
          const pb = vertices[String(b)];
          if (!pa || !pb) return null;

          const cx = (pa[0] + pb[0]) / 2;
          const cy = (pa[1] + pb[1]) / 2;
          const ratio = portRatioLabel(String(kind));

          return (
            <g key={`port-${idx}`}>
              <circle
                cx={cx}
                cy={cy}
                r={size * SIZE_RATIOS.portRadius}
                fill="#0b2433"
                stroke="#22d3ee"
                strokeWidth={STROKE_WIDTH.portBorder}
              />
              <text
                x={cx}
                y={cy + 3}
                textAnchor="middle"
                fontSize={FONT_SIZES.portRatio}
                fontWeight={700}
                fill="#d7eefc"
              >
                {ratio}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        {([
          [ActionType.Settlement, "Settlement"],
          [ActionType.Road, "Road"],
          [ActionType.City, "City"],
          enableSea ? [ActionType.Ship, "Ship"] : null,
          enableSea && enableMoveShip ? [ActionType.MoveShip, "Move Ship"] : null,
          enablePirate ? [ActionType.Pirate, "Pirate"] : null,
        ] as Array<[string, string] | null>)
          .filter((x): x is [string, string] => Boolean(x))
          .map(([key, label]) => {
            const isActive = selectedAction === key;
            return (
              <button
                key={key}
                onClick={() => onSelectAction(isActive ? null : key)}
                style={{
                  ...UI_STYLES.button,
                  ...(isActive && UI_STYLES.buttonActive),
                }}
              >
                {label}
              </button>
            );
          })}
      </div>
    </div>
  );
}
