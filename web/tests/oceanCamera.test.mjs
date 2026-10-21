import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { Box3, Group, PerspectiveCamera, Vector3 } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

const compiled = await build({
  stdin: { contents: `export * from "./src/board3d/coordinates";
    export * from "./src/board3d/model"; export * from "./src/board3d/oceanGeometry";
    export * from "./src/board3d/environment";
    export * from "./tests/fixtures/publicFog";`,
    resolveDir: fileURLToPath(new URL("../", import.meta.url)), loader: "ts" },
  bundle: true, write: false, platform: "node", format: "esm", external: ["react"],
});
const { cameraFootprint, cameraFrame, createRenderModel, buildOceanLayout, buildOceanFrameStrip,
  oceanClearance, ambientBoatPose, publicFogFixture, TILE_TOP, BOARD_RIM_TOP } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

// Public geometry scaffolding from shipped recipes, not a gameplay/map generator.
// In particular this test neither chooses Base numbers nor evaluates legal moves.
function recipeGeometry(name) {
  const recipe = JSON.parse(readFileSync(new URL(`../../app/assets/maps/${name}.json`, import.meta.url)));
  const size = recipe.size ?? 58;
  const tiles = recipe.tiles.map((t, index) => ({ ...t, index,
    terrain: t.terrain === "random" ? "forest" : t.terrain,
    number: t.number === "random" ? 5 : t.number,
    center: [size * Math.sqrt(3) * (t.q + t.r / 2), size * 1.5 * t.r] }));
  const vertices = {}, ids = new Map(), edge_adj_hexes = {};
  for (const [index, tile] of tiles.entries()) {
    const corners = Array.from({ length: 6 }, (_, i) => {
      const angle = (30 + 60 * i) * Math.PI / 180;
      const p = [tile.center[0] + size * Math.cos(angle), tile.center[1] + size * Math.sin(angle)];
      const key = p.map(n => Math.round(n / .5)).join(",");
      if (!ids.has(key)) { ids.set(key, ids.size); vertices[ids.get(key)] = p; }
      return ids.get(key);
    });
    corners.forEach((v, i) => {
      const key = [v, corners[(i + 1) % 6]].sort((a, b) => a - b).join(",");
      (edge_adj_hexes[key] ??= []).push(index);
    });
  }
  const edges = Object.keys(edge_adj_hexes).map(k => k.split(",").map(Number));
  return { size, tiles, vertices, edges, edge_adj_hexes, occupied_v: {}, occupied_e: {},
    occupied_ships: {}, ports: (recipe.ports ?? []).map(p => [p.edge, p.type]),
    robber_tile: recipe.robber_tile ?? 0, pirate_tile: recipe.pirate_tile ?? null, rules_config: recipe.rules };
}
const boards = Object.fromEntries([
  "base_standard", "seafarers_official_new_shores_3", "seafarers_official_new_shores_4",
  "seafarers_official_four_islands_3", "seafarers_official_four_islands_4",
].map(name => [name, recipeGeometry(name)]));
boards.seven = publicFogFixture("normal");
boards.fifty = publicFogFixture("large");

const assets = new Map();
async function assetPoints(relative, terrain = false) {
  if (!assets.has(relative)) {
    const bytes = readFileSync(new URL(`../public/models/${relative}.glb`, import.meta.url));
    const { scene } = await new GLTFLoader().parseAsync(
      bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "");
    const root = new Group(); root.add(scene);
    if (terrain) { root.rotation.y = Math.PI / 2; root.scale.setScalar(1 / 1.2); root.position.y = .11 / 1.2; }
    root.updateMatrixWorld(true);
    const result = [];
    const boxCorners = bounds => [bounds.min.x, bounds.max.x].flatMap(x => [bounds.min.y, bounds.max.y]
      .flatMap(y => [bounds.min.z, bounds.max.z].map(z => [x, y, z])));
    scene.traverse(node => {
      if (!node.isMesh) return;
      // Mesh bounds conservatively contain every exported vertex. Checking the
      // eight corners is sufficient for a convex camera frustum, without making
      // this test scale with the visual asset's detailed triangle count.
      result.push(...boxCorners(new Box3().setFromObject(node)));
    });
    const bounds = new Box3().setFromObject(root);
    const corners = boxCorners(bounds);
    assets.set(relative, { points: result, bounds, corners });
  }
  return assets.get(relative);
}
const terrains = Object.fromEntries(await Promise.all([
  "forest", "fields", "pasture", "hills", "mountains", "desert", "gold", "sea",
].map(async name => [name, await assetPoints(`terrain/${name}`, true)])));
const city = await assetPoints("pieces/city"), ship = await assetPoints("pieces/ship-pilot");

function overview(state, rings, aspect, frameVisible = true) {
  const model = createRenderModel(state), ocean = buildOceanLayout(state.tiles, state.size, rings);
  const frame = buildOceanFrameStrip(ocean.loops, .08, .245, .035);
  const decoration = frameVisible ? Array.from({ length: frame.positions.length / 3 }, (_, i) =>
    frame.positions.slice(i * 3, i * 3 + 3))
    : ocean.boundary.flatMap(edge => [edge.start, edge.end].map(p => [p[0], BOARD_RIM_TOP, p[2]]));
  const points = [...cameraFootprint(model), ...decoration];
  const fit = cameraFrame(model.bounds, aspect, 38, points);
  const camera = new PerspectiveCamera(38, aspect, Math.max(.01, model.bounds.radius / 100), fit.distance * 6);
  camera.position.set(...fit.position); camera.lookAt(...fit.target); camera.updateMatrixWorld(true);
  return { model, ocean, points, fit, camera };
}
function inside(camera, point, label) {
  const p = new Vector3(...point).project(camera);
  assert.ok(Number.isFinite(p.x) && Math.abs(p.x) < 1 && Math.abs(p.y) < 1 && Math.abs(p.z) < 1,
    `${label}: clipped ${point} -> ${p.toArray()}`);
}

for (const [name, state] of Object.entries(boards)) {
  test(`${name}: one/two-ring overview contains real relief, frame, ports and outer piece positions`, () => {
    const original = JSON.stringify(state);
    for (const rings of [1, 2]) for (const aspect of [.7, 1.64, 2.4]) {
      const { model, points, camera } = overview(state, rings, aspect);
      for (const point of points) inside(camera, point, `${name}/${rings}/${aspect} footprint`);
      for (const tile of model.tiles) {
        for (const point of terrains[tile.terrain]?.points ?? []) inside(camera,
          [tile.position[0] + point[0], point[1], tile.position[2] + point[2]], `${name} actual terrain`);
        // The token's actual radius/offset; all displayed numbers share this geometry.
        for (const x of [-.42, .42]) for (const z of [-.42, .42]) inside(camera,
          [tile.position[0] + x, TILE_TOP + .11, tile.position[2] + .18 + z], `${name} number`);
      }
      // Reserve all public vertices/edges, so a later city/ship does not reset fit.
      for (const [x, z] of Object.values(state.vertices)) {
        for (const p of city.corners) inside(camera, [x / state.size + p[0],
          BOARD_RIM_TOP + p[1], z / state.size + p[2]], `${name} possible outer city`);
      }
      for (const edge of state.edges) {
        const a = state.vertices[edge[0]], b = state.vertices[edge[1]];
        const angle = -Math.atan2(b[1] - a[1], b[0] - a[0]), length = Math.hypot(b[0] - a[0], b[1] - a[1]) / state.size;
        for (const p of ship.corners) {
          const x = p[0] * length * .88, z = p[2];
          inside(camera, [(a[0] + b[0]) / state.size / 2 + Math.cos(angle) * x + Math.sin(angle) * z,
            TILE_TOP + .06 + p[1], (a[1] + b[1]) / state.size / 2 - Math.sin(angle) * x + Math.cos(angle) * z], `${name} possible ship`);
        }
      }
    }
    assert.equal(JSON.stringify(state), original);
  });
}

test("Fog reveal, ownership, turn updates and ship presentation preserve the same public camera fit", () => {
  const state = publicFogFixture("large");
  const before = cameraFootprint(createRenderModel(state));
  const revealed = { ...state, tiles: state.tiles.map((t, i) => ({ ...t, visibility: "revealed",
    terrain: i % 2 ? "sea" : "mountains", number: i % 2 ? null : 8 })),
    occupied_v: {}, occupied_e: {}, occupied_ships: {}, turn: 1, tick: 99, shipModel: "glb" };
  assert.deepEqual(cameraFootprint(createRenderModel(revealed)), before);
  for (const rings of [1, 2]) {
    assert.deepEqual(overview(state, rings, 1.64).fit, overview(revealed, rings, 1.64).fit);
  }
});

test("overview reset is deterministic after zoom, resize and a frame visibility toggle", () => {
  const state = boards.seafarers_official_new_shores_4;
  const initial = overview(state, 1, 1.64), zoomed = initial.camera;
  zoomed.position.sub(new Vector3(...initial.fit.target)).multiplyScalar(.68).add(new Vector3(...initial.fit.target));
  zoomed.updateMatrixWorld(true);
  const resized = overview(state, 1, .7), restored = overview(state, 1, 1.64);
  assert.ok(resized.fit.distance > initial.fit.distance);
  assert.deepEqual(restored.fit, initial.fit);
  const noFrame = overview(state, 1, 1.64, false);
  assert.ok(noFrame.fit.distance <= initial.fit.distance);
  assert.deepEqual(overview(state, 1, 1.64).fit, initial.fit);
});

test("different official world-space sizes remain unchanged when fitting decorative geometry", () => {
  const base = createRenderModel(boards.base_standard), shores = createRenderModel(boards.seafarers_official_new_shores_4);
  const baseBefore = JSON.stringify(base.tiles.map(t => t.position)), shoresBefore = JSON.stringify(shores.tiles.map(t => t.position));
  assert.ok(shores.bounds.width > base.bounds.width && shores.bounds.depth > base.bounds.depth);
  overview(boards.base_standard, 2, 1.64); overview(boards.seafarers_official_new_shores_4, 2, 1.64);
  assert.equal(JSON.stringify(createRenderModel(boards.base_standard).tiles.map(t => t.position)), baseBefore);
  assert.equal(JSON.stringify(createRenderModel(boards.seafarers_official_new_shores_4).tiles.map(t => t.position)), shoresBefore);
});

test("Base ambient boats stay outside one/two-ring ocean and frame for their complete routes", () => {
  const state = boards.base_standard, model = createRenderModel(state);
  const original = JSON.stringify(model);
  const before = oceanClearance(model);
  for (const rings of [1, 2]) {
    const ocean = buildOceanLayout(state.tiles, state.size, rings);
    const positions = ocean.cells.map(c => c.position), clearance = oceanClearance(model, positions);
    assert.ok(clearance > before);
    const frame = buildOceanFrameStrip(ocean.loops, .08, .245, .035);
    const radius = Math.max(...frame.footprint.map(p => Math.hypot(
      p[0] - model.bounds.center[0], p[2] - model.bounds.center[2])));
    // Each current boat period is below1000s. One hour covers every phase;
    // clearance is measured against the whole frame's enclosing circle, so
    // corners between sample times cannot introduce an untested cell gap.
    for (let boat = 0; boat < 3; boat++) for (let seconds = 0; seconds <= 3600; seconds++) {
      const { position } = ambientBoatPose(model.bounds.center, clearance, boat, seconds);
      assert.ok(Math.hypot(position[0] - model.bounds.center[0], position[2] - model.bounds.center[2])
        > radius + .5, "entire scaled boat clears the complete physical board");
    }
    // The path's ellipse never contracts below the supplied clearance; the
    // frame/boat radial margin therefore also holds continuously between ticks.
    assert.ok(clearance > radius + .5);
  }
  assert.equal(oceanClearance(model, []), before, "before mode keeps its original route");
  assert.equal(JSON.stringify(model), original);
});
