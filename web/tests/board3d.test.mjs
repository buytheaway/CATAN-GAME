import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { PerspectiveCamera, Vector3 } from "three";

const compiled = await build({
  stdin: {
    contents: 'export * from "./coordinates"; export * from "./model"; export * from "./materials"; export * from "./preview"; export * from "./resources";',
    resolveDir: fileURLToPath(new URL("../src/board3d/", import.meta.url)),
    loader: "ts",
  },
  bundle: true, write: false, platform: "node", format: "esm",
});
const { toScenePosition, tilePosition, edgePlacement, boardBounds, cameraFrame, cameraFootprint, TILE_TOP,
  createRenderModel, terrainStyle, playerColor, portAppearance, buildPreview, targetColor, tileFeedback,
  terrainVariation, createVisualResources } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

function snapshot(overrides = {}) {
  return {
    size: 58,
    tiles: [
      { q: 0, r: 0, center: [0, 0], terrain: "forest", number: 6 },
      { q: 1, r: 0, center: [Math.sqrt(3) * 58, 0], terrain: "gold", number: 8 },
      { q: 0, r: 1, center: [Math.sqrt(3) * 29, 87], terrain: "sea", number: null },
    ],
    vertices: { 7: [58, 0], 42: [58, 58], 81: [0, 58] },
    edges: [[42, 7], [7, 81]],
    occupied_e: { "7,42": 0 }, occupied_ships: { "7,81": 1 },
    occupied_v: { 7: [0, 1], 81: [3, 2] },
    ports: [[[42, 7], "2:1:wood"], [[7, 81], "3:1"]],
    robber_tile: 0, robbers: [0, 1], pirate_tile: 2,
    ...overrides,
  };
}

function freeze(value) {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}

test("server XY maps to scene XZ with independent visual elevation and map size", () => {
  assert.deepEqual(toScenePosition([116, -58], 58, 0.4), [2, 0.4, -1]);
  assert.deepEqual(toScenePosition([200, 100], 100), [2, 0, 1]);
  assert.deepEqual(toScenePosition([58, 58], 0), [1, 0, 1]);
});

test("snapshot centers take priority; axial fallback matches the server convention", () => {
  assert.deepEqual(tilePosition({ q: 100, r: 100, center: [58, -116] }, 58), [1, 0, -2]);
  const axial = tilePosition({ q: 2, r: -1 }, 58);
  assert.equal(axial[0], Math.sqrt(3) * 1.5);
  assert.equal(axial[2], -1.5);
  assert.deepEqual(tilePosition({ q: 0, r: 0 }, 58), [0, 0, 0]);
});

test("road placement follows snapshot endpoints, including reversed edge IDs", () => {
  const road = edgePlacement([2, 0, 1], [2, 0, 4]);
  assert.deepEqual([road.position[0], road.position[2]], [2, 2.5]);
  assert.equal(road.length, 3);
  assert.equal(road.rotation, -Math.PI / 2);
  const reversed = edgePlacement([2, 0, 4], [2, 0, 1]);
  assert.equal(reversed.length, 3);
  assert.deepEqual(reversed.position, road.position);
});

test("bounds include offset, asymmetric maps and vertices, without a preset shape", () => {
  const model = createRenderModel(snapshot({
    tiles: [{ center: [5800, -580], terrain: "sea" }, { center: [7540, -1160], terrain: "desert" }],
    vertices: { 42: [8120, -1450] }, edges: [], ports: [],
    occupied_v: {}, occupied_e: {}, occupied_ships: {}, robbers: [], robber_tile: 0, pirate_tile: null,
  }));
  assert.equal(model.tiles.length, 2);
  assert.equal(model.bounds.minX, 99);
  assert.equal(model.bounds.maxX, 141);
  assert.equal(model.bounds.minZ, -26);
  assert.equal(model.bounds.maxZ, -9);
  assert.deepEqual(model.bounds.center, [120, 0, -17.5]);
});

test("auto-fit adapts to narrow/wide canvases and keeps a translated board as target", () => {
  const bounds = boardBounds([[10, 0, -8], [20, 0, -2]]);
  const wide = cameraFrame(bounds, 2);
  const narrow = cameraFrame(bounds, 0.7);
  assert.equal(wide.target[0], 15);
  assert.equal(wide.target[2], -5);
  assert.ok(narrow.distance > wide.distance);
  assert.ok(wide.position[1] > wide.target[1]);
  assert.ok(wide.position[2] > wide.target[2]);
  assert.ok(Object.values(boardBounds([])).flat().every(v => typeof v !== "number" || Number.isFinite(v)));
});

test("actual perspective camera contains all board corners after resize or a larger map", () => {
  for (const points of [[[0, 0, 0], [8, 0, 6]], [[-30, 0, 40], [12, 0, 46]]]) {
    const bounds = boardBounds(points);
    for (const aspect of [0.7, 1, 2.4]) {
      const frame = cameraFrame(bounds, aspect);
      const camera = new PerspectiveCamera(38, aspect, 0.01, 1000);
      camera.position.set(...frame.position);
      camera.lookAt(...frame.target);
      camera.updateMatrixWorld();
      for (const x of [bounds.minX, bounds.maxX]) {
        for (const z of [bounds.minZ, bounds.maxZ]) {
          for (const y of [0, 1]) {
            const point = new Vector3(x, y, z).project(camera);
            assert.ok(Math.abs(point.x) < 1 && Math.abs(point.y) < 1);
          }
        }
      }
    }
  }
});

test("all eight terrains have distinct readable colors and silhouettes; unknown data stays neutral", () => {
  const terrains = ["forest", "hills", "pasture", "fields", "mountains", "desert", "sea", "gold"];
  const styles = terrains.map(terrainStyle);
  assert.equal(new Set(styles.map(s => s.color)).size, 8);
  assert.equal(new Set(styles.map(s => s.hint)).size, 8);
  assert.notEqual(terrainStyle("gold").hint, terrainStyle("fields").hint);
  assert.equal(terrainStyle("unknown").hint, "none");
});

test("pieces use the existing six player colors, including owner zero", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5].map(playerColor),
    ["#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#14b8a6"]);
  assert.equal(playerColor(20), "#ffffff");
});

test("projection preserves original tile/vertex/edge IDs and snapshot terrain/numbers/ownership", () => {
  const source = snapshot();
  const model = createRenderModel(source);
  assert.deepEqual(model.tiles.map(t => [t.tileIndex, t.terrain, t.number]),
    [[0, "forest", 6], [1, "gold", 8], [2, "sea", null]]);
  assert.deepEqual(model.roads.map(r => [r.edge, r.owner]), [[[42, 7], 0]]);
  assert.deepEqual(model.ships.map(r => [r.edge, r.owner]), [[[7, 81], 1]]);
  assert.deepEqual(model.buildings.map(b => [b.vertexId, b.owner, b.level]), [[7, 0, 1], [81, 3, 2]]);
  assert.deepEqual(model.robbers.map(r => r.tileIndex), [0, 1]);
  assert.equal(model.pirate.tileIndex, 2);
});

test("ports retain the exact snapshot edge/kind, expose resource labels and fit within bounds", () => {
  const model = createRenderModel(snapshot());
  assert.deepEqual(model.ports.map(p => [p.edge, p.kind]), [[[42, 7], "2:1:wood"], [[7, 81], "3:1"]]);
  assert.equal(portAppearance("3:1").label, "3:1");
  for (const resource of ["wood", "brick", "sheep", "wheat", "ore"]) {
    assert.equal(portAppearance(`2:1:${resource}`).label, `2:1\n${resource}`);
  }
  for (const port of model.ports) {
    assert.ok(port.position[0] > model.bounds.minX && port.position[0] < model.bounds.maxX);
    assert.ok(port.position[2] > model.bounds.minZ && port.position[2] < model.bounds.maxZ);
  }
});

test("rendering projection accepts frozen state, never mutates it and evaluates no gameplay", () => {
  const source = freeze(snapshot({ phase: "setup", turn: 99, legal: { pid: 99 }, players: [{ res: {} }] }));
  const before = JSON.stringify(source);
  const first = createRenderModel(source);
  assert.equal(JSON.stringify(source), before);
  const otherTurn = createRenderModel({ ...source, phase: "main", turn: 0, legal: {}, players: [] });
  assert.deepEqual(otherTurn, first);
  assert.equal("legal" in first, false);
  assert.equal("players" in first, false);
});

test("missing optional ports/ships and stale piece coordinates do not invent new IDs", () => {
  const model = createRenderModel(snapshot({ ports: undefined, occupied_ships: {},
    occupied_v: { 999: [0, 1] }, edges: [[7, 999]], robbers: [999], pirate_tile: 999 }));
  assert.deepEqual(model.ports, []);
  assert.deepEqual(model.buildings, []);
  assert.deepEqual(model.roads, []);
  assert.deepEqual(model.ships, []);
  assert.deepEqual(model.robbers, []);
  assert.equal(model.pirate, null);
});

const previewInteraction = action => ({ action, legal: { pid: 0 },
  targets: { vertices: [42], edges: [[42, 7]], sources: [], tiles: [] },
  selection: { waiting: false, victim: null, shipSource: null },
});

test("four build previews preserve server targets, owner zero and existing piece transforms without mutation", () => {
  const source = freeze(snapshot());
  const before = JSON.stringify(source);
  for (const action of ["settlement", "city", "road", "ship"]) {
    const interaction = freeze(previewInteraction(action));
    const preview = buildPreview(source, interaction, action === "city" || action === "settlement" ? "v:42" : "e:7,42");
    assert.equal(preview.kind, action);
    if (preview.building) {
      assert.equal(preview.building.vertexId, 42);
      assert.equal(preview.building.owner, 0);
      assert.deepEqual([preview.building.position[0], preview.building.position[2]], [1, 1]);
      assert.equal(preview.building.level, action === "city" ? 2 : 1);
    } else {
      assert.deepEqual(preview.edge.edge, [42, 7]);
      assert.equal(preview.edge.owner, 0);
      assert.deepEqual(preview.edge.position, edgePlacement([1, 0, 1], [1, 0, 0]).position);
      assert.equal(preview.edge.rotation, Math.PI / 2);
    }
  }
  assert.equal(JSON.stringify(source), before);
});

test("previews disappear on leave, waiting, victim choice, changed server targets or missing personal legal", () => {
  const state = snapshot(), interaction = previewInteraction("settlement");
  assert.equal(buildPreview(state, interaction, null), null);
  assert.equal(buildPreview(state, interaction, "v:7"), null); // Valid coordinate, absent from server targets.
  for (const changed of [
    { legal: undefined }, { selection: { waiting: true } }, { selection: { victim: { tile: 0 } } },
    { targets: { ...interaction.targets, vertices: [] } }, { action: "move_ship" }, { action: "robber" },
  ]) assert.equal(buildPreview(state, { ...interaction, ...changed }, "v:42"), null);
  assert.equal(buildPreview({ ...state, vertices: {} }, interaction, "v:42"), null);
  assert.equal(buildPreview({ ...state, vertices: {} }, previewInteraction("ship"), "e:7,42"), null);
});

test("selected feedback has its own persistent accent instead of becoming hover feedback", () => {
  assert.notEqual(targetColor(false), targetColor(true));
  assert.notEqual(targetColor(true), targetColor(false, true));
  assert.equal(targetColor(true, true), targetColor(false, true));
});

test("tile feedback preserves terrain color and cannot illuminate another tile sharing the pool", async () => {
  const pool = createVisualResources(); pool.retain();
  const color = terrainStyle("forest").color;
  const neutral = pool.standard(color);
  const hover = pool.standard(color, false, tileFeedback(true, false, false));
  const selected = pool.standard(color, false, tileFeedback(false, false, true));
  assert.equal(neutral.emissiveIntensity, 0);
  assert.equal(hover.color.getHexString(), neutral.color.getHexString());
  assert.ok(hover.emissiveIntensity > 0);
  assert.ok(selected.emissiveIntensity > hover.emissiveIntensity);
  assert.equal(tileFeedback(true, true, true), tileFeedback(false, false, true));
  assert.equal(tileFeedback(false, false, false), undefined);
  assert.equal(pool.standard(color, false, tileFeedback(true, false, false)), hover);
  assert.equal(pool.standard(color), neutral);
  let disposed = 0;
  hover.addEventListener("dispose", () => disposed++);
  pool.release(); await Promise.resolve();
  assert.equal(disposed, 1);
});

test("terrain variation is deterministic, modest and varied across a 50-tile board", () => {
  const variations = Array.from({ length: 50 }, (_, i) => terrainVariation(i));
  assert.deepEqual(variations, Array.from({ length: 50 }, (_, i) => terrainVariation(i)));
  assert.equal(new Set(variations.map(v => v.rotation)).size, 50);
  for (const v of variations) {
    assert.ok(Math.abs(v.rotation) <= 0.16 && Math.abs(v.offset) <= 0.03);
    assert.ok(v.scale >= 0.94 && v.scale <= 1.06);
    assert.ok(v.height >= 0.88 && v.height <= 1.12);
  }
});

test("port placards remain small finite shared geometry with a visible bevel", async () => {
  const pool = createVisualResources(); pool.retain();
  const geo = pool.geometry("port"); geo.computeBoundingBox();
  assert.equal(pool.geometry("port"), geo);
  assert.ok(geo.boundingBox.max.x < 0.33 && geo.boundingBox.max.z < 0.25);
  assert.ok(geo.boundingBox.max.y > 0.055 && geo.boundingBox.max.y < 0.08);
  assert.ok(Array.from(geo.attributes.position.array).every(Number.isFinite));
  pool.release(); await Promise.resolve();
});

test("camera fits actual tile rims and port labels on asymmetric 50-hex and narrow layouts", () => {
  const model = createRenderModel(snapshot({ tiles: Array.from({ length: 50 }, (_, i) => ({
    center: [580 + (i % 10) * 101 + Math.floor(i / 10) * 50, -1160 + Math.floor(i / 10) * 87],
    terrain: "sea",
  })) }));
  const points = cameraFootprint(model);
  for (const aspect of [0.7, 1.45, 2.4]) {
    const frame = cameraFrame(model.bounds, aspect, 38, points);
    assert.ok(frame.distance <= cameraFrame(model.bounds, aspect).distance);
    const camera = new PerspectiveCamera(38, aspect, 0.01, 1000);
    camera.position.set(...frame.position); camera.lookAt(...frame.target); camera.updateMatrixWorld();
    for (const point of points) {
      const projected = new Vector3(...point).project(camera);
      assert.ok(Math.abs(projected.x) < 1 && Math.abs(projected.y) < 1);
    }
  }
  const changed = createRenderModel(snapshot({ ...snapshot(), tiles: model.tiles.map(t => ({
    center: [t.position[0] * 58, t.position[2] * 58], terrain: "sea",
  })), occupied_e: {}, occupied_v: {} }));
  assert.deepEqual(cameraFootprint(changed), points); // Ownership updates cannot reset framing.
});

test("scene resources reuse geometry/materials and ghost materials do not write depth", async () => {
  const pool = createVisualResources(); pool.retain();
  assert.equal(pool.geometry("house"), pool.geometry("house"));
  assert.equal(pool.standard(playerColor(0)), pool.standard(playerColor(0)));
  assert.equal(pool.flat("#ffffff", 0.5), pool.flat("#ffffff", 0.5));
  const ghost = pool.standard(playerColor(0), true);
  assert.notEqual(ghost, pool.standard(playerColor(0)));
  assert.ok(ghost.transparent && ghost.opacity < 1 && !ghost.depthWrite);
  pool.release(); await Promise.resolve();
});

test("scene unmount disposes shared geometry and both material kinds, once per resource", async () => {
  const pool = createVisualResources(); pool.retain();
  const resources = [pool.geometry("hex"), pool.ring(0.18, 0.26), pool.standard("#ffffff"), pool.flat("#ffffff", 0.5)];
  const disposed = resources.map(() => 0);
  resources.forEach((r, i) => r.addEventListener("dispose", () => disposed[i]++));
  pool.release(); await Promise.resolve();
  assert.deepEqual(disposed, [1, 1, 1, 1]);
});

test("React StrictMode effect replay retains live scene resources until the actual unmount", async () => {
  const pool = createVisualResources(); pool.retain();
  const geo = pool.geometry("road"); let disposed = 0;
  geo.addEventListener("dispose", () => disposed++);
  pool.release(); pool.retain(); await Promise.resolve();
  assert.equal(disposed, 0); assert.equal(pool.geometry("road"), geo);
  pool.release(); await Promise.resolve(); assert.equal(disposed, 1);
});

test("bevelled tiles keep the original logical surface height and finite pointy-top geometry", async () => {
  const pool = createVisualResources(); pool.retain();
  const geo = pool.geometry("hex"); geo.computeBoundingBox();
  assert.ok(Math.abs(geo.boundingBox.max.y - TILE_TOP) < 1e-6);
  assert.ok(geo.boundingBox.min.y > 0 && geo.boundingBox.min.y < TILE_TOP);
  assert.ok(geo.boundingBox.max.z > geo.boundingBox.max.x); // Pointy-top, matching server topology.
  assert.ok(Array.from(geo.attributes.position.array).every(Number.isFinite));
  pool.release(); await Promise.resolve();
});
