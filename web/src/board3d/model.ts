import { edgeId } from "../board/constants";
import { isHiddenTile, isKnownLand, isKnownSea, isPublicPort, publicTileVisual } from "../board/publicTiles";
import { boardBounds, edgePlacement, tilePosition, toScenePosition, TILE_TOP } from "./coordinates";
import type { BoardRenderModel, BoardSnapshot, Point3D, RenderEdge } from "./types";

/** Read-only presentation projection. Never rebuild the graph or evaluate rules. */
export function createRenderModel(state: BoardSnapshot): BoardRenderModel {
  const tiles = state.tiles.map((tile, tileIndex) => ({
    tileIndex, position: tilePosition(tile, state.size),
    ...publicTileVisual(tile),
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
    if (!isPublicPort(state, edge)) return [];
    const [a, b] = edge;
    if (!vertices[a] || !vertices[b]) return [];
    const { position: anchor, rotation } = edgePlacement(vertices[a], vertices[b]);
    const land = (state.edge_adj_hexes?.[edgeId(edge)] ?? [])
      .filter(i => isKnownLand(state.tiles[i]));
    // Local coast normal also works on inward-facing archipelago shores.
    // Historical snapshots without valid coast adjacency retain the fallback.
    const origin = land.length === 1 ? tiles[land[0]].position : baseBounds.center;
    const dx = anchor[0] - origin[0];
    const dz = anchor[2] - origin[2];
    const length = Math.hypot(dx, dz) || 1;
    // Label offset is visual only; dock stays attached to the supplied port edge.
    const position: Point3D = [anchor[0] + dx / length * 0.72, TILE_TOP, anchor[2] + dz / length * 0.72];
    return [{ edge, kind, anchor, position, rotation, endpoints: [vertices[a], vertices[b]] as [Point3D, Point3D] }];
  });
  const coast = state.edges.flatMap(edge => {
    const adjacent = state.edge_adj_hexes?.[edgeId(edge)] ?? [];
    if (adjacent.some(i => isHiddenTile(state.tiles[i]))) return [];
    const land = adjacent.some(i => isKnownLand(state.tiles[i]));
    const water = adjacent.length === 1 || adjacent.some(i => isKnownSea(state.tiles[i]));
    if (!land || !water || !vertices[edge[0]] || !vertices[edge[1]]) return [];
    const placement = edgePlacement(vertices[edge[0]], vertices[edge[1]]);
    return [{ edge, ...placement, position: [placement.position[0], TILE_TOP - .02, placement.position[2]] as Point3D }];
  });
  const robberIds = state.robbers?.length ? state.robbers : [state.robber_tile];
  const robbers = robberIds.flatMap(tileIndex => tiles[tileIndex]?.visibility === "revealed"
    ? [{ tileIndex, position: tiles[tileIndex].position }] : []);
  const pirate = state.pirate_tile != null && tiles[state.pirate_tile]?.visibility === "revealed"
    ? { tileIndex: state.pirate_tile, position: tiles[state.pirate_tile].position } : null;
  return {
    tiles, roads, ships, buildings, ports, coast, robbers, pirate,
    bounds: boardBounds([...tiles.map(t => t.position), ...Object.values(vertices), ...ports.map(p => p.position)]),
  };
}
