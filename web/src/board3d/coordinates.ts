import type { Tile } from "../components/BoardView.types";
import { publicTileCenter } from "../board/publicTiles";
import type { BoardBounds, BoardRenderModel, Point3D, RenderPort } from "./types";

export const TILE_TOP = 0.26;
// Visible contact plane shared by finalized terrain rims and their procedural fallback.
// Logical hit geometry continues to use TILE_TOP.
export const BOARD_RIM_TOP = .21833333333333332;
// The existing coastal strip ends at BOARD_RIM_TOP. Keep decorative water
// slightly below it so their overlapping shoreline surfaces cannot z-fight.
export const DECORATIVE_WATER_TOP = BOARD_RIM_TOP - .008;
export const TERRAIN_FALLBACK_OFFSET: Point3D = [0, BOARD_RIM_TOP - TILE_TOP, 0];

/** The .05-high coastal strip ends at the visible rim, below piece foundations. */
export function coastVisualPosition(position: Point3D): Point3D {
  return [position[0], BOARD_RIM_TOP - .05 / 2, position[2]];
}

function coordinateScale(size: number): number {
  return Number.isFinite(size) && size > 0 ? size : 58;
}

/** Server XY is the board plane; Three Y is exclusively visual elevation. */
export function toScenePosition([x, y]: [number, number], size: number, elevation = 0): Point3D {
  const scale = coordinateScale(size);
  return [x / scale, elevation, y / scale];
}

export function tilePosition(tile: Tile, size: number): Point3D {
  return toScenePosition(publicTileCenter(tile, size), size);
}

export function edgePlacement(a: Point3D, b: Point3D) {
  const dx = b[0] - a[0];
  const dz = b[2] - a[2];
  return {
    position: [(a[0] + b[0]) / 2, TILE_TOP + 0.06, (a[2] + b[2]) / 2] as Point3D,
    length: Math.hypot(dx, dz),
    // A box's local X axis follows the existing edge, independent of ID order.
    rotation: -Math.atan2(dz, dx),
  };
}

export function boardBounds(points: Point3D[], margin = 1): BoardBounds {
  const valid = points.filter(p => Number.isFinite(p[0]) && Number.isFinite(p[2]));
  const xs = valid.length ? valid.map(p => p[0]) : [0];
  const zs = valid.length ? valid.map(p => p[2]) : [0];
  const minX = Math.min(...xs) - margin;
  const maxX = Math.max(...xs) + margin;
  const minZ = Math.min(...zs) - margin;
  const maxZ = Math.max(...zs) + margin;
  const width = maxX - minX;
  const depth = maxZ - minZ;
  return {
    minX, maxX, minZ, maxZ, width, depth,
    center: [(minX + maxX) / 2, 0, (minZ + maxZ) / 2],
    radius: Math.max(1, Math.hypot(width, depth) / 2),
  };
}

/** Pull the visual badge closer to its existing edge; game topology/IDs remain untouched. */
export function portLabelPosition(port: Pick<RenderPort, "position" | "anchor">): Point3D {
  return [port.anchor[0] + (port.position[0] - port.anchor[0]) * 0.66, port.position[1],
    port.anchor[2] + (port.position[2] - port.anchor[2]) * 0.66];
}

/** Both branches use the original port edge endpoints, with no nearest-vertex inference. */
export function portConnectors(port: RenderPort) {
  const label = portLabelPosition(port);
  return port.endpoints.map((endpoint, i) => ({ vertexId: port.edge[i],
    ...edgePlacement(endpoint, label), start: endpoint, end: label }));
}

/** Public geometry only: elevation/occupancy changes must not reset a player's camera. */
export function cameraFootprint(model: Pick<BoardRenderModel, "tiles" | "ports">): Point3D[] {
  const outline = model.tiles.flatMap(t => {
    const rim = Array.from({ length: 6 }, (_, i): Point3D =>
      [t.position[0] + Math.sin(i * Math.PI / 3), TILE_TOP, t.position[2] + Math.cos(i * Math.PI / 3)]);
    // Reserve the same modest relief over every tile, including public Fog slots.
    // A reveal or loaded GLB then cannot change the fit or disclose hidden terrain.
    const relief = [-.65, .65].flatMap(x => [-.65, .65].map((z): Point3D =>
      [t.position[0] + x, 1.42, t.position[2] + z]));
    // Cover current/future pieces at perimeter vertices and edges regardless of
    // ownership. This includes both ship renderers without reading legal targets.
    const pieces = Array.from({ length: 6 }, (_, i): Point3D =>
      [t.position[0] + 1.4 * Math.sin(i * Math.PI / 3), .95,
        t.position[2] + 1.4 * Math.cos(i * Math.PI / 3)]);
    return [...rim, ...relief, ...pieces];
  });
  model.ports.forEach(p => {
    const position = portLabelPosition(p);
    const rotation = p.rotation - Math.round(p.rotation / Math.PI) * Math.PI;
    for (const x of [-.35, .35]) for (const z of [-.27, .27])
      outline.push([position[0] + x * Math.cos(rotation) + z * Math.sin(rotation), .4,
        position[2] - x * Math.sin(rotation) + z * Math.cos(rotation)]);
  });
  return outline;
}

export function cameraFrame(bounds: Pick<BoardBounds, "center" | "width" | "depth">, aspect: number, fov = 38,
  footprint?: Point3D[]) {
  const vertical = fov * Math.PI / 360;
  const horizontal = Math.atan(Math.tan(vertical) * Math.max(0.1, aspect));
  const direction = [0.12, 1.7, 1.2];
  const length = Math.hypot(...direction);
  const forward = direction.map(v => v / length);
  const planar = Math.hypot(forward[0], forward[2]);
  const right = [forward[2] / planar, 0, -forward[0] / planar];
  const up = [-forward[1] * forward[0] / planar, planar, -forward[1] * forward[2] / planar];
  const dot = (a: number[], b: number[]) => a.reduce((sum, v, i) => sum + v * b[i], 0);
  const points: Point3D[] = [];
  // Rectangle fallback also supports callers which have only bounds.
  for (const x of [-bounds.width / 2, bounds.width / 2]) {
    for (const z of [-bounds.depth / 2, bounds.depth / 2]) {
      for (const y of [-TILE_TOP, 0.9]) {
        points.push([x, y, z]);
      }
    }
  }
  const actual = footprint?.length ? footprint.map(p =>
    [p[0] - bounds.center[0], p[1] - TILE_TOP, p[2] - bounds.center[2]]) : points;
  // Balance both sides of each frustum, rather than treating the ground center
  // as the visual center of a tilted, elevated island. Fit all supplied points.
  const extent = (axis: number[], tangent: number, sign: number) =>
    Math.max(...actual.map(p => dot(p, forward) + sign * dot(p, axis) / tangent));
  const left = extent(right, Math.tan(horizontal), -1), rightExtent = extent(right, Math.tan(horizontal), 1);
  const bottom = extent(up, Math.tan(vertical), -1), top = extent(up, Math.tan(vertical), 1);
  const offsetX = (rightExtent - left) * Math.tan(horizontal) / 2;
  const offsetY = (top - bottom) * Math.tan(vertical) / 2;
  const distance = Math.max(1, (left + rightExtent) / 2, (top + bottom) / 2) * 1.045;
  const target = right.map((v, i) => [bounds.center[0], TILE_TOP, bounds.center[2]][i] + v * offsetX + up[i] * offsetY) as Point3D;
  return {
    target, distance,
    position: forward.map((v, i) => target[i] + v * distance) as Point3D,
  };
}
