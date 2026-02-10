/**
 * Board view constants and configurations
 */

export const SQRT3 = 1.7320508075688772;

export const TERRAIN_COLORS: Record<string, string> = {
  forest: "#1f7a3f",
  hills: "#d06016",
  pasture: "#7edc92",
  fields: "#f3c550",
  mountains: "#96a3b4",
  desert: "#d6c8a0",
  sea: "#0b4a6f",
  gold: "#eab308",
} as const;

export const PLAYER_COLORS = [
  "#ef4444",
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#a855f7",
  "#14b8a6",
] as const;

export enum ActionType {
  Settlement = "settlement",
  Road = "road",
  City = "city",
  Ship = "ship",
  MoveShip = "move_ship",
  Pirate = "pirate",
}

export enum CommandType {
  PlaceSettlement = "place_settlement",
  UpgradeCity = "upgrade_city",
  PlaceRoad = "place_road",
  BuildShip = "build_ship",
  MoveShip = "move_ship",
  MoveRobber = "move_robber",
  MovePirate = "move_pirate",
}

export enum GamePhase {
  Setup = "setup",
  Main = "main",
}

export const UI_STYLES = {
  container: {
    width: "100%",
    background: "#081a24",
    borderRadius: 12,
    padding: 8,
  },
  infoText: {
    color: "#bcd",
    fontSize: 12,
    marginBottom: 6,
  },
  svg: {
    display: "block" as const,
    background: "#0b2a3a",
    borderRadius: 12,
  },
  button: {
    padding: "6px 10px",
    borderRadius: 8,
    border: "1px solid #193042",
    background: "#0b2433",
    color: "#d7eefc",
    fontWeight: 600 as const,
  },
  buttonActive: {
    background: "#123549",
  },
} as const;

export const SHADOW_FILTERS = {
  tile: {
    id: "tileShadow",
    dx: "2",
    dy: "2",
    stdDeviation: "2",
    floodColor: "#03131c",
    floodOpacity: "0.6",
  },
  token: {
    id: "tokenShadow",
    dx: "1",
    dy: "1",
    stdDeviation: "1.5",
    floodColor: "#000",
    floodOpacity: "0.4",
  },
} as const;

export const SIZE_RATIOS = {
  tokenRadius: 0.28,
  robberRadius: 0.18,
  pirateRadius: 0.16,
  portRadius: 0.18,
  bounds: 1.6,
} as const;

export const STROKE_WIDTH = {
  road: 10,
  ship: 8,
  hexBorder: 2,
  settlement: 1,
  city: 1,
  portBorder: 1.5,
  hexHitArea: 14,
} as const;

export const NUMBER_COLORS = {
  default: "#0b1220",
  highlight: "#ef4444", // For 6 and 8
} as const;

export const FONT_SIZES = {
  hexNumber: 14,
  robberText: 12,
  pirateText: 11,
  portRatio: 10,
} as const;

export const STROKE_DASHARRAY = {
  ship: "6 4",
} as const;

export const CURSOR_STYLES = {
  default: "default" as const,
  pointer: "pointer" as const,
} as const;

export const SETUP_TYPES = {
  settlement: "settlement",
  road: "road",
} as const;
