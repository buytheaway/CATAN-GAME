import type { Tile } from "../components/BoardView.types";
import type { BoardBounds, BoardRenderModel, Point3D } from "./types";

export const TILE_TOP = 0.26;

function coordinateScale(size: number): number {
  return Number.isFinite(size) && size > 0 ? size : 58;
}

/** Server XY is the board plane; Three Y is exclusively visual elevation. */
export function toScenePosition([x, y]: [number, number], size: number, elevation = 0): Point3D {
  const scale = coordinateScale(size);
  return [x / scale, elevation, y / scale];
}

export function tilePosition(tile: Tile, size: number): Point3D {
  if (tile.center) return toScenePosition(tile.center, size);
  const q = tile.q ?? 0;
  const r = tile.r ?? 0;
  // Axial fallback uses the same pointy-top orientation as the server.
  return [Math.sqrt(3) * (q + r / 2), 0, 1.5 * r];
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

/** Visual footprint includes tile rims and port labels, without empty bounding-box corners. */
export function cameraFootprint(model: Pick<BoardRenderModel, "tiles" | "ports">): Point3D[] {
  const outline = model.tiles.flatMap(t => Array.from({ length: 6 }, (_, i): Point3D =>
    [t.position[0] + Math.sin(i * Math.PI / 3), 0, t.position[2] + Math.cos(i * Math.PI / 3)]));
  model.ports.forEach(p => {
    for (const x of [-0.48, 0.48]) for (const z of [-0.48, 0.48])
      outline.push([p.position[0] + x, 0, p.position[2] + z]);
  });
  return outline.flatMap(([x, , z]) => [[x, 0, z], [x, 0.95, z]] as Point3D[]);
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
  let distance = 1;
  const points: Point3D[] = [];
  // Rectangle fallback also supports callers which have only bounds.
  for (const x of [-bounds.width / 2, bounds.width / 2]) {
    for (const z of [-bounds.depth / 2, bounds.depth / 2]) {
      for (const y of [-TILE_TOP, 0.9]) {
        points.push([x, y, z]);
      }
    }
  }
  for (const point of footprint?.length ? footprint.map(p =>
    [p[0] - bounds.center[0], p[1] - TILE_TOP, p[2] - bounds.center[2]]) : points) {
    distance = Math.max(distance,
      dot(point, forward) + Math.abs(dot(point, right)) / Math.tan(horizontal),
      dot(point, forward) + Math.abs(dot(point, up)) / Math.tan(vertical));
  }
  distance *= 1.08;
  const target: Point3D = [bounds.center[0], TILE_TOP, bounds.center[2]];
  return {
    target, distance,
    position: forward.map((v, i) => target[i] + v * distance) as Point3D,
  };
}
