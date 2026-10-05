/**
 * Type definitions for BoardView component
 */

export type EdgeTuple = [number, number];

export interface Coordinates {
  x: number;
  y: number;
}

export interface VertexCoordinates {
  [key: string]: [number, number];
}

export interface OccupiedVertex {
  [key: string]: [number, number] | undefined;
}

export interface OccupiedEdge {
  [key: string]: number | undefined;
}

export interface LegalMoves {
  pid: number;
  settlements: number[];
  roads: EdgeTuple[];
  cities: number[];
  ships: EdgeTuple[];
  road_free?: boolean;
  robber_tiles?: number[];
  pirate_tiles?: number[];
  robber_victims?: Record<string, number[]>;
  pirate_victims?: Record<string, number[]>;
  move_ship?: { sources: EdgeTuple[]; targets: Record<string, EdgeTuple[]> };
}

export interface Tile {
  q?: number;
  r?: number;
  center?: [number, number];
  number?: number | null;
  terrain: string;
}

export type Port = [EdgeTuple, string];

export interface RulesConfig {
  target_vp?: number;
  robber_count?: number;
  enable_gold?: boolean;
  enable_seafarers?: boolean;
  max_ships?: number;
  enable_move_ship?: boolean;
  enable_pirate?: boolean;
}

export interface GameBounds {
  minX: number;
  minY: number;
  width: number;
  height: number;
}

export interface GameState {
  tiles: Tile[];
  size: number;
  vertices: VertexCoordinates;
  edges: EdgeTuple[];
  occupied_e: OccupiedEdge;
  occupied_ships: OccupiedEdge;
  occupied_v: OccupiedVertex;
  edge_adj_hexes: Record<string, number[]>;
  robber_tile: number;
  robbers?: number[];
  pirate_tile?: number | null;
  pending_action: string | null;
  pending_pid: number | null;
  phase: string;
  setup_need?: string;
  turn: number;
  rules_config?: RulesConfig;
  legal?: LegalMoves;
  ports?: Port[];
  players?: { pid: number; name: string; color?: string | null }[];
}

export interface MoveShipState {
  from: EdgeTuple | null;
}

export interface BoardViewProps {
  state: GameState;
  interaction: import("../board/interaction").BoardInteraction;
}

export interface Command {
  type: string;
  [key: string]: any;
}

export interface SetupSettlementCommand extends Command {
  type: "place_settlement";
  vid: number;
  setup: boolean;
}

export interface UpgradeCityCommand extends Command {
  type: "upgrade_city";
  vid: number;
}

export interface PlaceRoadCommand extends Command {
  type: "place_road";
  eid: EdgeTuple;
  setup: boolean;
}

export interface BuildShipCommand extends Command {
  type: "build_ship";
  eid: EdgeTuple;
}

export interface MoveShipCommand extends Command {
  type: "move_ship";
  from_eid: EdgeTuple;
  to_eid: EdgeTuple;
}

export interface MoveRobberCommand extends Command {
  type: "move_robber";
  tile: number;
}

export interface MovePirateCommand extends Command {
  type: "move_pirate";
  tile: number;
}
