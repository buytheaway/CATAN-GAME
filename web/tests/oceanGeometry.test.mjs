import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const compiled = await build({
  entryPoints: [fileURLToPath(new URL("../src/board3d/oceanGeometry.ts", import.meta.url))],
  bundle: true, write: false, platform: "node", format: "esm",
});
const { buildOceanLayout, buildOceanFrameStrip } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);
const directions = [[0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1], [1, 0]];
const id = ({ q, r }) => `${q},${r}`;
const pointId = p => p.join(",");
const area = loop => loop.reduce((sum, p, i) => {
  const b = loop[(i + 1) % loop.length];
  return sum + p[0] * b[2] - b[0] * p[2];
}, 0) / 2;
const recipe = name => JSON.parse(readFileSync(new URL(`../../app/assets/maps/${name}.json`, import.meta.url), "utf8"));

function verifyBoundary(layout) {
  const segments = new Set(layout.boundary.map(e => `${pointId(e.start)}:${pointId(e.end)}`));
  assert.equal(segments.size, layout.boundary.length, "no repeated frame edge");
  assert.equal(layout.loops.flat().length, layout.boundary.length, "every exterior edge appears in a closed loop");
  for (const loop of layout.loops) {
    assert.ok(loop.length >= 6);
    assert.ok(area(loop) > 0, "outside is consistently to the right of the loop");
    assert.equal(new Set(loop.map(pointId)).size, loop.length, "closing point is not duplicated");
    for (let i = 0; i < loop.length; i++) {
      const a = loop[i], b = loop[(i + 1) % loop.length];
      assert.ok(segments.has(`${pointId(a)}:${pointId(b)}`), "no missing joins");
      assert.ok(Math.abs(Math.hypot(a[0] - b[0], a[2] - b[2]) - 1) < 1e-9);
    }
  }
}

test("Base radius-two board has exactly one 18-cell ring or two 18/24-cell rings", () => {
  const tiles = recipe("base_standard").tiles;
  const one = buildOceanLayout(tiles, 58), two = buildOceanLayout(tiles, 58, 2);
  assert.equal(one.cells.length, 18);
  assert.equal(two.cells.length, 42);
  assert.equal(two.cells.filter(c => c.ring === 1).length, 18);
  assert.equal(two.cells.filter(c => c.ring === 2).length, 24);
  assert.equal(one.boundary.length, 42);
  assert.equal(two.boundary.length, 54);
  assert.deepEqual(two.cells.filter(c => c.ring === 1), one.cells);
  verifyBoundary(one);
  verifyBoundary(two);
});

for (const name of ["base_standard", "seafarers_official_new_shores_3", "seafarers_official_new_shores_4",
  "seafarers_official_four_islands_3", "seafarers_official_four_islands_4"]) {
  test(`${name}: real authoritative footprint is surrounded without duplicate playable/frame cells`, () => {
    const { tiles, size } = recipe(name);
    const original = new Set(tiles.map(id));
    const source = JSON.stringify(tiles);
    for (const rings of [0, 1, 2]) {
      const layout = buildOceanLayout(tiles, size ?? 58, rings);
      const decoration = new Map(layout.cells.map(c => [id(c), c]));
      assert.equal(decoration.size, layout.cells.length);
      assert.equal(layout.loops.length, 1);
      assert.equal(layout.holes.length, 0);
      verifyBoundary(layout);
      for (const cell of layout.cells) {
        assert.ok(!original.has(id(cell)), "physical-frame sea remains playable, not duplicated");
        assert.equal(cell.position[0], Math.sqrt(3) * (cell.q + cell.r / 2));
        assert.deepEqual(cell.position.slice(1), [0, 1.5 * cell.r]);
        assert.ok(directions.some(([dq, dr]) => cell.ring === 1 ? original.has(id({ q: cell.q + dq, r: cell.r + dr }))
          : decoration.get(id({ q: cell.q + dq, r: cell.r + dr }))?.ring === cell.ring - 1));
      }
      if (rings) for (const tile of tiles) for (const [dq, dr] of directions) {
        const neighbor = id({ q: tile.q + dq, r: tile.r + dr });
        assert.ok(original.has(neighbor) || decoration.has(neighbor), "complete first surrounding ring");
      }
      assert.deepEqual(layout, buildOceanLayout([...tiles].reverse(), size ?? 58, rings), "stable input order");
    }
    assert.equal(JSON.stringify(tiles), source, "public snapshot is not mutated");
  });
}

test("an irregular concave footprint retains a continuous true hex perimeter", () => {
  const tiles = [{ q: 0, r: 0 }, { q: 1, r: 0 }, { q: 2, r: 0 }, { q: 0, r: 1 }, { q: 0, r: 2 }];
  for (const rings of [0, 1, 2]) {
    const layout = buildOceanLayout(tiles, 58, rings);
    verifyBoundary(layout);
    assert.equal(layout.loops.length, 1);
    assert.ok(layout.boundary.some(e => e.start[0] !== e.end[0] && e.start[2] !== e.end[2]));
  }
});

test("enclosed holes are identified separately and never receive ocean or an outer frame", () => {
  const tiles = directions.map(([q, r]) => ({ q, r }));
  for (const rings of [0, 1, 2]) {
    const layout = buildOceanLayout(tiles, 58, rings);
    assert.ok(!layout.cells.some(c => c.q === 0 && c.r === 0));
    assert.equal(layout.holes.length, 1);
    assert.equal(layout.holes[0].length, 6);
    assert.ok(area(layout.holes[0]) < 0);
    verifyBoundary(layout);
    assert.equal(layout.loops.length, 1);
  }
});

test("separated footprint components each get closed loops without bridging empty space", () => {
  const layout = buildOceanLayout([{ q: -8, r: 0 }, { q: 8, r: 0 }], 58);
  assert.equal(layout.cells.length, 12);
  assert.equal(layout.loops.length, 2);
  verifyBoundary(layout);
});

test("Fog and reveal have identical decoration; forbidden fields are never read", () => {
  const geometry = recipe("base_standard").tiles.map(({ q, r }) => ({ q, r }));
  const hidden = geometry.map(g => Object.defineProperties({ ...g }, Object.fromEntries(
    ["terrain", "number", "visibility", "index", "private", "fog_pool"].map(field => [field, {
      get() { throw new Error(`must not inspect ${field}`); },
    }]))));
  assert.deepEqual(buildOceanLayout(hidden, 58), buildOceanLayout(geometry, 58));
  const serialized = JSON.stringify(buildOceanLayout(hidden, 58));
  for (const field of ["terrain", "number", "visibility", "tileIndex", "fog_pool", "vertex", "edgeId"]) {
    assert.ok(!serialized.includes(`"${field}"`), `decoration has no ${field}`);
  }
});

test("historical center-only coordinates invert the original axial grid at any valid map size", () => {
  for (const size of [32, 58, 100]) {
    const tiles = recipe("base_standard").tiles;
    const centers = tiles.map(({ q, r }) => ({ center: [size * Math.sqrt(3) * (q + r / 2), size * 1.5 * r] }));
    assert.deepEqual(buildOceanLayout(centers, size), buildOceanLayout(tiles, size));
  }
});

test("finite public centers take priority over mismatched axial metadata, and off-grid centers are not guessed", () => {
  const center = [Math.sqrt(3) * 58 * (2 - 1 / 2), -1.5 * 58];
  assert.deepEqual(buildOceanLayout([{ q: 100, r: 100, center }], 58),
    buildOceanLayout([{ q: 2, r: -1 }], 58));
  assert.equal(buildOceanLayout([{ q: 0, r: 0, center: [10, 10] }], 58).cells.length, 0);
  assert.equal(buildOceanLayout([{ q: 0, r: 0 }, { q: 1, r: 0, center: [10, 10] }], 58).cells.length, 0);
});

test("duplicate and malformed geometry is handled without invented origin cells", () => {
  const tile = { q: 2, r: -3 };
  const bad = [{}, { q: NaN, r: 0 }, { q: .2, r: 0 }, { center: [Infinity, 0] }];
  assert.deepEqual(buildOceanLayout([tile, tile, ...bad], 58), buildOceanLayout([tile], 58));
  for (const size of [0, -1, NaN, Infinity]) assert.deepEqual(buildOceanLayout([tile], size),
    { cells: [], boundary: [], loops: [], holes: [] });
  assert.equal(buildOceanLayout([{ q: 0, r: 0 }, { q: 100000, r: 100000 }], 58).cells.length, 0);
  assert.equal(buildOceanLayout([], 58).loops.length, 0);
});

test("frame strips share mitered joins with finite upward-facing non-overlapping band triangles", () => {
  for (const name of ["base_standard", "seafarers_official_new_shores_4"]) {
    const layout = buildOceanLayout(recipe(name).tiles, 58);
    const { positions, indices } = buildOceanFrameStrip(layout.loops, .08, .218);
    const count = layout.loops.flat().length;
    assert.equal(positions.length, count * 2 * 3);
    assert.equal(indices.length, count * 2 * 3);
    assert.ok(positions.every(Number.isFinite));
    for (let i = 1; i < positions.length; i += 3) assert.equal(positions[i], .218);
    for (let i = 0; i < indices.length; i += 3) {
      const points = indices.slice(i, i + 3).map(index => positions.slice(index * 3, index * 3 + 3));
      const [a, b, c] = points;
      const normalY = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]);
      assert.ok(normalY > 0, "every band triangle faces up without a folded miter");
    }
  }
  assert.deepEqual(buildOceanFrameStrip([], .08), { positions: [], indices: [], footprint: [] });
  assert.deepEqual(buildOceanFrameStrip([[[0, 0, 0]]], -1), { positions: [], indices: [], footprint: [] });
});

test("optional outer skirt shares closed corner joins and keeps camera footprint at the top", () => {
  const layout = buildOceanLayout(recipe("base_standard").tiles, 58);
  const strip = buildOceanFrameStrip(layout.loops, .08, .245, .035);
  const count = layout.loops.flat().length;
  assert.equal(strip.positions.length, count * 4 * 3);
  assert.equal(strip.indices.length, count * 4 * 3);
  assert.equal(strip.footprint.length, count);
  assert.ok(strip.footprint.every(p => p[1] === .245));
  assert.equal(strip.positions.filter((_, i) => i % 3 === 1 && strip.positions[i] === .035).length, count);
  const invalid = buildOceanFrameStrip(layout.loops, .08, .245, .3);
  assert.deepEqual(invalid, { positions: [], indices: [], footprint: [] });
});

test("optional inner lip closes only the exposed height above water with inward-facing shared joins", () => {
  const waterTop = .21833333333333332, frameTop = .245;
  const layout = buildOceanLayout(recipe("base_standard").tiles, 58);
  const loop = layout.loops[0], count = loop.length;
  const strip = buildOceanFrameStrip(layout.loops, .08, frameTop, .035, waterTop);
  assert.equal(strip.positions.length, count * 6 * 3);
  assert.equal(strip.indices.length, count * 6 * 3);
  const lipBase = count * 4;
  const vertex = index => strip.positions.slice(index * 3, index * 3 + 3);
  for (let i = 0; i < count; i++) {
    const a = loop[i], b = loop[(i + 1) % count];
    assert.deepEqual(vertex(lipBase + i * 2), [a[0], frameTop, a[2]]);
    assert.deepEqual(vertex(lipBase + i * 2 + 1), [a[0], waterTop, a[2]]);
    const face = strip.indices.slice(count * 12 + i * 6, count * 12 + i * 6 + 3).map(vertex);
    const [p, q, r] = face;
    const u = q.map((v, j) => v - p[j]), v = r.map((n, j) => n - p[j]);
    const normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
      u[0] * v[1] - u[1] * v[0]];
    const towardWater = [-(b[2] - a[2]), 0, b[0] - a[0]];
    assert.ok(normal.reduce((sum, n, j) => sum + n * towardWater[j], 0) > 0);
    assert.equal(normal[1], 0);
  }
  assert.deepEqual(buildOceanFrameStrip(layout.loops, .08, frameTop, .035, frameTop),
    { positions: [], indices: [], footprint: [] });
});
