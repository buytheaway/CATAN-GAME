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
}

export interface Tile {
  center?: [number, number];
  number?: number;
  terrain: string;
}

export interface Port {
  edge: EdgeTuple;
  kind: string;
}

export interface RulesConfig {
  enable_seafarers?: boolean;
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
  pending_action: string;
  pending_pid: number;
  phase: string;
  setup_need?: string;
  turn: number;
  rules_config?: RulesConfig;
  legal?: LegalMoves;
  ports?: Port[];
}

export interface MoveShipState {
  from: EdgeTuple | null;
}

export interface BoardViewProps {
  state: GameState;
  youPid: number;
  selectedAction: string | null;
  onSendCmd: (cmd: Command) => void;
  onSelectAction: (action: string | null) => void;
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
