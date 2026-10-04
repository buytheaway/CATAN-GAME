import { edgeId } from "../board/constants";
import { boardBounds, edgePlacement, tilePosition, toScenePosition, TILE_TOP } from "./coordinates";
import type { BoardRenderModel, BoardSnapshot, Point3D, RenderEdge } from "./types";

/** Read-only presentation projection. Never rebuild the graph or evaluate rules. */
export function createRenderModel(state: BoardSnapshot): BoardRenderModel {
  const tiles = state.tiles.map((tile, tileIndex) => ({
    tileIndex, position: tilePosition(tile, state.size),
    terrain: tile.terrain, number: tile.number ?? null,
  }));
  const vertices = Object.fromEntries(Object.entries(state.vertices).map(([id, point]) =>
    [id, toScenePosition(point, state.size, TILE_TOP)]));
  const baseBounds = boardBounds([...tiles.map(t => t.position), ...Object.values(vertices)]);
  const roads: RenderEdge[] = [];
  const ships: RenderEdge[] = [];
  for (const edge of state.edges) {
    const [a, b] = edge;
    if (!vertices[a] || !vertices[b]) continue;
    const key = edgeId(edge);
    const placement = edgePlacement(vertices[a], vertices[b]);
    const roadOwner = state.occupied_e[key];
    const shipOwner = state.occupied_ships[key];
    if (roadOwner !== undefined) roads.push({ edge, owner: roadOwner, ...placement });
    if (shipOwner !== undefined) ships.push({ edge, owner: shipOwner, ...placement });
  }
  const buildings = Object.entries(state.occupied_v).flatMap(([id, occupied]) => {
    if (!occupied || !vertices[id]) return [];
    return [{ vertexId: Number(id), position: vertices[id], owner: occupied[0], level: occupied[1] }];
  });
  const ports = (state.ports ?? []).flatMap(([edge, kind]) => {
    const [a, b] = edge;
    if (!vertices[a] || !vertices[b]) return [];
    const { position: anchor, rotation } = edgePlacement(vertices[a], vertices[b]);
    const dx = anchor[0] - baseBounds.center[0];
    const dz = anchor[2] - baseBounds.center[2];
    const length = Math.hypot(dx, dz) || 1;
    // Label offset is visual only; dock stays attached to the supplied port edge.
    const position: Point3D = [anchor[0] + dx / length * 0.72, TILE_TOP, anchor[2] + dz / length * 0.72];
    return [{ edge, kind, anchor, position, rotation }];
  });
  const robberIds = state.robbers?.length ? state.robbers : [state.robber_tile];
  const robbers = robberIds.flatMap(tileIndex => tiles[tileIndex]
    ? [{ tileIndex, position: tiles[tileIndex].position }] : []);
  const pirate = state.pirate_tile != null && tiles[state.pirate_tile]
    ? { tileIndex: state.pirate_tile, position: tiles[state.pirate_tile].position } : null;
  return {
    tiles, roads, ships, buildings, ports, robbers, pirate,
    bounds: boardBounds([...tiles.map(t => t.position), ...Object.values(vertices), ...ports.map(p => p.position)]),
  };
}
