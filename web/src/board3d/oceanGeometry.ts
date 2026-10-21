import type { Point3D } from "./types";

export type OceanRings = 0 | 1 | 2;
type PublicGeometry = { q?: number; r?: number; center?: readonly [number, number] };
type Axial = { q: number; r: number };
type Corner = readonly [number, number];

export interface OceanLayout {
  /** Decoration only: deliberately no server tile index or gameplay ID. */
  cells: { q: number; r: number; ring: number; position: Point3D }[];
  boundary: { start: Point3D; end: Point3D }[];
  /** Exterior loops, counterclockwise in XZ; closing vertex is not repeated. */
  loops: Point3D[][];
  /** Enclosed gaps are never filled or framed as exterior ocean. */
  holes: Point3D[][];
}

// Edge i joins the corners at angles 30+60*i and 30+60*(i+1).
const DIRECTIONS: readonly Corner[] = [[0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1], [1, 0]];
// Integer keys avoid rounding drift at shared corners. X is sqrt(3)/2; Z is 1/2.
const CORNERS: readonly Corner[] = [[1, 1], [0, 2], [-1, 1], [-1, -1], [0, -2], [1, -1]];
const key = (q: number, r: number) => `${q},${r}`;
const sceneCorner = ([x, z]: Corner): Point3D => [x * Math.sqrt(3) / 2, 0, z / 2];
const emptyLayout = (): OceanLayout => ({ cells: [], boundary: [], loops: [], holes: [] });

function axial(tile: PublicGeometry, size: number): Axial | null {
  const safe = (q: number, r: number) => Number.isSafeInteger(q) && Number.isSafeInteger(r)
    && Number.isSafeInteger(2 * q + r + 2) && Number.isSafeInteger(3 * r + 2);
  const center = tile.center;
  if (center && Number.isFinite(center[0]) && Number.isFinite(center[1])) {
    // Match publicTileCenter: a supplied valid center is the renderer's source.
    const r = center[1] / size / 1.5;
    const q = center[0] / size / Math.sqrt(3) - r / 2;
    const qi = Math.round(q), ri = Math.round(r);
    return safe(qi, ri) && Math.abs(qi - q) < 1e-6 && Math.abs(ri - r) < 1e-6 ? { q: qi, r: ri } : null;
  }
  return safe(tile.q!, tile.r!) ? { q: tile.q!, r: tile.r! } : null;
}

/** Finite exterior flood; malformed enormous/sparse footprints cannot allocate unbounded work. */
function exterior(occupied: Map<string, Axial>, padding: number): Set<string> | null {
  const coordinates = [...occupied.values()];
  const minQ = Math.min(...coordinates.map(p => p.q)) - padding;
  const maxQ = Math.max(...coordinates.map(p => p.q)) + padding;
  const minR = Math.min(...coordinates.map(p => p.r)) - padding;
  const maxR = Math.max(...coordinates.map(p => p.r)) + padding;
  if (![minQ, maxQ, minR, maxR].every(Number.isSafeInteger)
    || (maxQ - minQ + 1) * (maxR - minR + 1) > 65536) return null;
  const queue: Axial[] = [{ q: minQ, r: minR }];
  const outside = new Set([key(minQ, minR)]);
  for (let i = 0; i < queue.length; i++) {
    for (const [dq, dr] of DIRECTIONS) {
      const q = queue[i].q + dq, r = queue[i].r + dr, id = key(q, r);
      if (q < minQ || q > maxQ || r < minR || r > maxR || occupied.has(id) || outside.has(id)) continue;
      outside.add(id);
      queue.push({ q, r });
    }
  }
  return outside;
}

function traceLoops(edges: { a: Corner; b: Corner }[]): Point3D[][] {
  const byStart = new Map(edges.map(edge => [key(...edge.a), edge]));
  const loops: Point3D[][] = [];
  while (byStart.size) {
    const first = byStart.values().next().value!;
    let edge = first;
    const loop: Point3D[] = [];
    do {
      loop.push(sceneCorner(edge.a));
      byStart.delete(key(...edge.a));
      if (key(...edge.b) === key(...first.a)) break;
      const next = byStart.get(key(...edge.b));
      // Invalid geometry never emits an open frame pretending to be complete.
      if (!next) return [];
      edge = next;
    } while (byStart.size);
    loops.push(loop);
  }
  return loops;
}

/**
 * Public footprint -> client-only decoration. Terrain, visibility, numbers,
 * server IDs, graph adjacency and private assignments are never inspected.
 * Missing/malformed geometry is skipped; unsafe whole footprints fail closed.
 */
export function buildOceanLayout(tiles: readonly PublicGeometry[], size: number, rings: OceanRings = 1): OceanLayout {
  if (!Number.isFinite(size) || size <= 0 || ![0, 1, 2].includes(rings)) return emptyLayout();
  const original = new Map<string, Axial>();
  for (const tile of tiles) {
    const point = axial(tile, size);
    // An existing rendered center off this grid cannot be safely surrounded by
    // approximate cells; omit the decoration for that whole malformed board.
    if (!point && tile.center && Number.isFinite(tile.center[0]) && Number.isFinite(tile.center[1])) return emptyLayout();
    if (point) original.set(key(point.q, point.r), point);
  }
  if (!original.size || original.size > 10000) return emptyLayout();
  const outside = exterior(original, rings + 1);
  if (!outside) return emptyLayout();
  const occupied = new Map(original);
  const cells: OceanLayout["cells"] = [];
  let frontier = [...original.values()];
  for (let ring = 1; ring <= rings; ring++) {
    const next = new Map<string, Axial>();
    for (const point of frontier) for (const [dq, dr] of DIRECTIONS) {
      const q = point.q + dq, r = point.r + dr, id = key(q, r);
      if (!occupied.has(id) && outside.has(id)) next.set(id, { q, r });
    }
    frontier = [...next.values()].sort((a, b) => a.q - b.q || a.r - b.r);
    for (const point of frontier) {
      occupied.set(key(point.q, point.r), point);
      cells.push({ ...point, ring, position: [Math.sqrt(3) * (point.q + point.r / 2), 0, 1.5 * point.r] });
    }
  }
  const finalOutside = exterior(occupied, 1);
  if (!finalOutside) return emptyLayout();
  const outerEdges: { a: Corner; b: Corner }[] = [], holeEdges: typeof outerEdges = [];
  const ordered = [...occupied.values()].sort((a, b) => a.q - b.q || a.r - b.r);
  for (const { q, r } of ordered) DIRECTIONS.forEach(([dq, dr], i) => {
    const neighbor = key(q + dq, r + dr);
    if (occupied.has(neighbor)) return;
    const corner = (index: number): Corner => [2 * q + r + CORNERS[index][0], 3 * r + CORNERS[index][1]];
    const edge = { a: corner(i), b: corner((i + 1) % 6) };
    (finalOutside.has(neighbor) ? outerEdges : holeEdges).push(edge);
  });
  const loops = traceLoops(outerEdges);
  if (!loops.length) return emptyLayout();
  return { cells, boundary: outerEdges.map(edge => ({ start: sceneCorner(edge.a), end: sceneCorner(edge.b) })),
    loops, holes: traceLoops(holeEdges) };
}

/** Continuous outward mitered top band; shared joins replace overlapping edge boxes. */
export function buildOceanFrameStrip(loops: readonly (readonly Point3D[])[], width = .08,
  elevation = .21833333333333332, bottom?: number, innerBottom?: number) {
  const positions: number[] = [], indices: number[] = [], footprint: Point3D[] = [];
  const empty = () => ({ positions: [] as number[], indices: [] as number[], footprint: [] as Point3D[] });
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(elevation)
    || bottom !== undefined && (!Number.isFinite(bottom) || bottom >= elevation)
    || innerBottom !== undefined && (!Number.isFinite(innerBottom) || innerBottom >= elevation)) return empty();
  for (const loop of loops) {
    if (loop.length < 3) continue;
    if (loop.some(p => p.some(v => !Number.isFinite(v)))) return empty();
    const base = positions.length / 3;
    const outer: Point3D[] = [];
    for (let i = 0; i < loop.length; i++) {
      const before = loop[(i + loop.length - 1) % loop.length], point = loop[i], after = loop[(i + 1) % loop.length];
      const first = [point[0] - before[0], point[2] - before[2]];
      const second = [after[0] - point[0], after[2] - point[2]];
      const a = Math.hypot(...first), b = Math.hypot(...second);
      if (!a || !b) return empty();
      const n1 = [first[1] / a, -first[0] / a], n2 = [second[1] / b, -second[0] / b];
      const denominator = 1 + n1[0] * n2[0] + n1[1] * n2[1];
      if (denominator < 1e-6) return empty();
      const offset = width / denominator;
      const outside: Point3D = [point[0] + (n1[0] + n2[0]) * offset,
        elevation, point[2] + (n1[1] + n2[1]) * offset];
      positions.push(point[0], elevation, point[2], ...outside);
      outer.push(outside);
      footprint.push(outside);
      const inner = base + i * 2, next = base + ((i + 1) % loop.length) * 2;
      indices.push(inner, next, next + 1, inner, next + 1, inner + 1);
    }
    if (bottom !== undefined) {
      const skirt = positions.length / 3;
      for (let i = 0; i < outer.length; i++) {
        const p = outer[i];
        // Separate normals preserve the flat top; adjacent skirt joins are shared.
        positions.push(...p, p[0], bottom, p[2]);
        const a = skirt + i * 2, b = skirt + ((i + 1) % outer.length) * 2;
        indices.push(a, b, b + 1, a, b + 1, a + 1);
      }
    }
    if (innerBottom !== undefined) {
      const lip = positions.length / 3;
      for (let i = 0; i < loop.length; i++) {
        const p = loop[i];
        // Stop exactly at the water top, with no coplanar body-side overlap.
        positions.push(p[0], elevation, p[2], p[0], innerBottom, p[2]);
        const a = lip + i * 2, b = lip + ((i + 1) % loop.length) * 2;
        // The inner face points toward the water, opposite the outside skirt.
        indices.push(a, b + 1, b, a, a + 1, b + 1);
      }
    }
  }
  return { positions, indices, footprint };
}
