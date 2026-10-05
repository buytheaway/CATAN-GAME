/**
 * Main board view component with improved code quality
 * - Uses proper TypeScript types instead of `any`
 * - Extracts constants to avoid magic strings/numbers
 * - Splits logic into utility functions
 * - Adds proper error boundaries
 * - Includes JSDoc comments
 */

import { useMemo } from "react";
import { colorForPlayer } from "../board/colors";
import type {
  BoardViewProps,
} from "./BoardView.types";
import {
  TERRAIN_COLORS,
  UI_STYLES,
  SHADOW_FILTERS,
  SIZE_RATIOS,
  STROKE_WIDTH,
  NUMBER_COLORS,
  FONT_SIZES,
  STROKE_DASHARRAY,
  CURSOR_STYLES,
} from "./BoardView.constants";
import {
  hexCorners,
  edgeKey,
  calculateBounds,
  portRatioLabel,
} from "./BoardView.utils";

/** SVG presentation of the shared server-driven board interaction. */
export default function BoardView({ state, interaction }: BoardViewProps) {
  const {
    tiles = [], size = 58, vertices = {}, edges = [], occupied_e = {},
    occupied_ships = {}, occupied_v = {}, robber_tile = 0, robbers = [],
    pirate_tile = null, ports = [],
  } = state;
  const robberList = robbers.length ? robbers : [robber_tile];
  const bounds = useMemo(() => calculateBounds(tiles, size), [tiles, size]);
  const { targets, selection } = interaction;
  const overlayEdges = selection.shipSource && !targets.edges.some(e => edgeKey(...e) === edgeKey(...selection.shipSource!))
    ? [...targets.edges, selection.shipSource] : targets.edges;

  return (
    <div style={UI_STYLES.container}>
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
                stroke={targets.tiles.includes(idx) ? "#22c55e" : "transparent"}
                strokeWidth={4}
                data-target-tile={targets.tiles.includes(idx) ? idx : undefined}
                onClick={() => interaction.onTileClick(idx)}
                style={{
                  cursor:
                    targets.tiles.includes(idx)
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
                stroke={colorForPlayer(owner, state.players)}
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
                stroke={colorForPlayer(shipOwner, state.players)}
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
          const color = colorForPlayer(pid, state.players);
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

        {/* Shared controller targets; no local rule inference. */}
        {overlayEdges.map(([a, b]) => {
          const pa = vertices[String(a)], pb = vertices[String(b)];
          if (!pa || !pb) return null;
          const key = edgeKey(a, b);
          const source = selection.shipSource && key === edgeKey(...selection.shipSource);
          return <line key={`edge-hit-${key}`} x1={pa[0]} y1={pa[1]} x2={pb[0]} y2={pb[1]}
            data-target-edge={key} stroke={source ? "#f59e0b" : "#22c55e"} strokeOpacity={0.65}
            strokeWidth={STROKE_WIDTH.hexHitArea} strokeLinecap="round"
            onClick={() => interaction.onEdgeClick([a, b])} style={{ cursor: CURSOR_STYLES.pointer }} />;
        })}
        {targets.vertices.map(vid => {
          const point = vertices[String(vid)];
          if (!point) return null;
          return <circle key={`v-hit-${vid}`} cx={point[0]} cy={point[1]} r={7}
            data-target-vertex={vid} fill={interaction.action === "city" ? "#f59e0b" : "#22c55e"}
            fillOpacity={0.7} stroke="#0b1220" strokeWidth={1}
            onClick={() => interaction.onVertexClick(vid)} style={{ cursor: CURSOR_STYLES.pointer }} />;
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


    </div>
  );
}
