import type { EdgeTuple, GameState } from "../components/BoardView.types";

export type Point3D = [number, number, number];
export type BoardSnapshot = Pick<GameState,
  "tiles" | "size" | "vertices" | "edges" | "ports" | "occupied_v" |
  "occupied_e" | "occupied_ships" | "robber_tile" | "robbers" | "pirate_tile" | "edge_adj_hexes" | "players" | "rules_config"
>;

export interface BoardBounds {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  width: number;
  depth: number;
  center: Point3D;
  radius: number;
}

export interface RenderTile {
  tileIndex: number;
  position: Point3D;
  terrain: string;
  number: number | null;
}

export interface RenderEdge {
  edge: EdgeTuple;
  position: Point3D;
  length: number;
  rotation: number;
  owner: number;
}

export interface RenderBuilding {
  vertexId: number;
  position: Point3D;
  owner: number;
  level: number;
}

export interface RenderPort {
  edge: EdgeTuple;
  anchor: Point3D;
  position: Point3D;
  rotation: number;
  kind: string;
  endpoints: [Point3D, Point3D];
}

// Derived mesh data only: no turn, resources, legal moves or commands.
export interface BoardRenderModel {
  tiles: RenderTile[];
  roads: RenderEdge[];
  ships: RenderEdge[];
  buildings: RenderBuilding[];
  ports: RenderPort[];
  coast: { edge: EdgeTuple; position: Point3D; length: number; rotation: number }[];
  robbers: { tileIndex: number; position: Point3D }[];
  pirate: { tileIndex: number; position: Point3D } | null;
  bounds: BoardBounds;
}
