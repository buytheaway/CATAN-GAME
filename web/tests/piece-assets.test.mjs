import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const compiled = await build({
  stdin: { contents: `export * from "./pieceAssets"; export * from "./pieceFeedback";
    export * from "./preview"; export * from "./coordinates"; export * from "./model";
    export {createVisualResources} from "./resources";
    export * from "../board/colors";
    export { Group, Mesh, MeshStandardMaterial, Box3, Vector3, Raycaster } from "three";
    export { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";`,
    resolveDir: fileURLToPath(new URL("../src/board3d/", import.meta.url)), loader: "ts" },
  bundle: true, write: false, platform: "node", format: "esm",
});
const { PIECE_ASSET_URLS, PIECE_CONTACT_Y, pieceOffset, createPieceAssetCache, createPieceMaterials,
  clonePieceScene, ignorePieceRaycast, appearanceScale, PIECE_APPEARANCE_MS, pieceSignatures, confirmedPlacements,
  buildPreview, replacesSettlement, edgePlacement, toScenePosition, coastVisualPosition, TILE_TOP, TERRAIN_FALLBACK_OFFSET, ROOM_COLORS, colorForPlayer,
  Group, Mesh, MeshStandardMaterial, Box3, Vector3, Raycaster, GLTFLoader, createVisualResources } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

const close = (actual, expected, label) => assert.ok(Math.abs(actual - expected) < 1e-6, `${label}: ${actual} != ${expected}`);
async function parse(relative) {
  const bytes = await readFile(new URL(`../public/models/${relative}.glb`, import.meta.url));
  return (await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "")).scene;
}
const assets = Object.fromEntries(await Promise.all(Object.keys(PIECE_ASSET_URLS).map(async kind => [kind, await parse(`pieces/${kind}`)])));
const meshes = scene => { const result = []; scene.traverse(node => { if (node.isMesh) result.push(node); }); return result; };
const allMaterials = scene => meshes(scene).flatMap(mesh => Array.isArray(mesh.material) ? mesh.material : [mesh.material]);

test("three finalized piece mappings share one concurrent/later load per type", async () => {
  const calls = [], cache = createPieceAssetCache(async url => { calls.push(url); return new Group(); });
  assert.deepEqual(PIECE_ASSET_URLS, { settlement: "/models/pieces/settlement.glb", city: "/models/pieces/city.glb", road: "/models/pieces/road.glb" });
  for (const kind of Object.keys(PIECE_ASSET_URLS)) {
    const requests = Array.from({ length: 15 }, () => cache(kind));
    const scenes = await Promise.all(requests);
    assert.ok(scenes.every(scene => scene === scenes[0]));
    assert.equal(await cache(kind), scenes[0]);
  }
  assert.deepEqual(calls, Object.values(PIECE_ASSET_URLS));
});

test("missing/throwing piece loads resolve local fallback once without breaking the other pieces", async () => {
  for (const fail of [() => Promise.reject(new Error("404")), () => { throw new Error("bad GLB"); }]) {
    const warnings = [], calls = [], cache = createPieceAssetCache(url => {
      calls.push(url); return url.endsWith("city.glb") ? fail() : Promise.resolve(assets.road);
    }, message => warnings.push(message));
    assert.deepEqual(await Promise.all([cache("city"), cache("city")]), [null, null]);
    assert.equal(await cache("city"), null);
    assert.equal(await cache("road"), assets.road);
    assert.equal(warnings.length, 1); assert.match(warnings[0], /city\.glb.*procedural piece fallback/);
    assert.deepEqual(calls, [PIECE_ASSET_URLS.city, PIECE_ASSET_URLS.road]);
  }
});

test("all six owner colors affect only PlayerColor and never other pieces or cached originals", () => {
  const pool = createPieceMaterials();
  for (const source of Object.values(assets)) {
    const original = allMaterials(source), before = original.map(m => ({ uuid: m.uuid, color: m.color.getHexString(), opacity: m.opacity }));
    const palette = Object.entries(ROOM_COLORS);
    const instances = palette.map(([id, hex], pid) => {
      const color = colorForPlayer(pid, [{ pid, color: id }]); assert.equal(color, hex);
      const scene = clonePieceScene(source, pool, color, false);
      allMaterials(scene).forEach((material, i) => {
        if (original[i].name === "PlayerColor") {
          assert.notEqual(material, original[i]); assert.equal(material.color.getHexString(), hex.slice(1));
        } else assert.equal(material, original[i]);
      });
      return scene;
    });
    instances.forEach((scene, i) => assert.equal(allMaterials(scene).find(m => m.name === "PlayerColor").color.getHexString(), palette[i][1].slice(1)));
    assert.deepEqual(original.map(m => ({ uuid: m.uuid, color: m.color.getHexString(), opacity: m.opacity })), before);
    const again = clonePieceScene(source, pool, palette[0][1], false);
    assert.notEqual(again, instances[0]);
    assert.equal(allMaterials(again).find(m => m.name === "PlayerColor"), allMaterials(instances[0]).find(m => m.name === "PlayerColor"));
    meshes(again).forEach((mesh, i) => assert.equal(mesh.geometry, meshes(source)[i].geometry));
  }
  pool.dispose();
});

test("ghost opacity is isolated from confirmed pieces and keeps neutral colors", () => {
  const pool = createPieceMaterials(), source = assets.city;
  const placed = clonePieceScene(source, pool, "#ef4444", false), ghost = clonePieceScene(source, pool, "#3b82f6", true);
  const neutralGhost = clonePieceScene(source, pool, "#22c55e", true);
  allMaterials(ghost).forEach((material, i) => {
    const original = allMaterials(source)[i];
    assert.notEqual(material, original); assert.equal(material.opacity, .46);
    assert.equal(material.depthWrite, false); assert.equal(material.transparent, true);
    assert.equal(allMaterials(placed)[i].opacity, 1); assert.equal(original.opacity, 1);
    if (material.name !== "PlayerColor") {
      assert.equal(material.color.getHex(), original.color.getHex());
      assert.equal(allMaterials(neutralGhost)[i], material);
    }
  });
  pool.dispose();
});

test("every GLB node ignores raycasting while the source and shared geometry remain usable", () => {
  const pool = createPieceMaterials();
  for (const source of Object.values(assets)) {
    source.updateMatrixWorld(true);
    const ray = new Raycaster(new Vector3(0, 3, 0), new Vector3(0, -1, 0));
    assert.ok(ray.intersectObject(source, true).length, "source geometry really intersects the test ray");
    for (const ghost of [false, true]) {
      const clone = clonePieceScene(source, pool, "#ef4444", ghost); clone.updateMatrixWorld(true);
      clone.traverse(node => assert.equal(node.raycast, ignorePieceRaycast));
      assert.deepEqual(ray.intersectObject(clone, true), []);
      meshes(clone).forEach((mesh, i) => { assert.equal(mesh.geometry, meshes(source)[i].geometry); assert.equal(mesh.castShadow, !ghost); });
      clone.position.x = 10; assert.equal(source.position.x, 0);
    }
  }
  pool.dispose();
});

test("real GLB bases contact the common terrain rim with original anchors and dimensions", async () => {
  const dimensions = { settlement: [.345811, .4195, .3055], city: [.500353, .5465, .434], road: [.884, .087, .144] };
  for (const [kind, source] of Object.entries(assets)) {
    const bounds = new Box3().setFromObject(source), size = bounds.getSize(new Vector3()).toArray();
    size.forEach((value, i) => close(value, dimensions[kind][i], `${kind} dimension ${i}`));
    close(bounds.min.y, 0, `${kind} source contact`); close(bounds.min.x + bounds.max.x, 0, `${kind} centered X`);
    close(bounds.min.z + bounds.max.z, 0, `${kind} centered Z`);
    const anchor = new Group(), offset = new Group();
    anchor.position.set(3, TILE_TOP + (kind === "road" ? .06 : 0), -2);
    offset.position.set(...pieceOffset(kind)); offset.add(source.clone(true)); anchor.add(offset); anchor.updateMatrixWorld(true);
    close(new Box3().setFromObject(anchor).min.y, PIECE_CONTACT_Y, `${kind} world contact`);
    assert.deepEqual(anchor.position.toArray(), [3, TILE_TOP + (kind === "road" ? .06 : 0), -2]);
  }
  for (const terrain of ["forest", "fields", "pasture", "hills", "mountains", "desert", "sea", "gold"]) {
    const scene = await parse(`terrain/${terrain}`); scene.scale.setScalar(1 / 1.2); scene.position.y = .11 / 1.2;
    scene.updateMatrixWorld(true);
    const rim = scene.getObjectByName(`Hex_${terrain[0].toUpperCase() + terrain.slice(1)}_Rim`); assert.ok(rim);
    close(new Box3().setFromObject(rim).max.y, PIECE_CONTACT_Y, `${terrain} common rim`);
  }
});

test("road local X and its .884 body length follow actual edge endpoints in both ID orders", () => {
  for (const [a, b] of [[[2, 0, -1], [6, 0, 2]], [[6, 0, 2], [2, 0, -1]], [[0, 0, 0], [0, 0, 3]]]) {
    const placement = edgePlacement(a, b), root = new Group(), length = new Group(), offset = new Group();
    root.position.set(...placement.position); root.rotation.y = placement.rotation; length.scale.x = placement.length;
    offset.position.set(...pieceOffset("road")); offset.add(assets.road.clone(true)); length.add(offset); root.add(length); root.updateMatrixWorld(true);
    const start = new Vector3(-.442, 0, 0).applyMatrix4(offset.matrixWorld), end = new Vector3(.442, 0, 0).applyMatrix4(offset.matrixWorld);
    close(start.distanceTo(end), placement.length * .884, "existing segment length");
    close((start.x + end.x) / 2, (a[0] + b[0]) / 2, "original midpoint X");
    close((start.z + end.z) / 2, (a[2] + b[2]) / 2, "original midpoint Z");
    const direction = end.clone().sub(start).normalize();
    close(direction.x, (b[0] - a[0]) / placement.length, "orientation X");
    close(direction.z, (b[2] - a[2]) / placement.length, "orientation Z");
    close(new Box3().setFromObject(root).min.y, PIECE_CONTACT_Y, "road has ground contact");
  }
});

test("visible procedural terrain meets the same piece contact plane while logical hit geometry stays unchanged", () => {
  const pool = createVisualResources(); pool.retain();
  const geometry = pool.geometry("hex"), material = new MeshStandardMaterial();
  const logical = new Mesh(geometry, material), visible = new Group(); visible.position.set(...TERRAIN_FALLBACK_OFFSET);
  visible.add(new Mesh(geometry, material));
  close(new Box3().setFromObject(logical).max.y, TILE_TOP, "logical surface unchanged");
  close(new Box3().setFromObject(visible).max.y, PIECE_CONTACT_Y, "fallback meets the GLB rim");
  const coast = new Mesh(pool.geometry("box"), material); coast.scale.set(1, .05, .12);
  coast.position.set(...coastVisualPosition([3, TILE_TOP - .02, -5]));
  close(new Box3().setFromObject(coast).max.y, PIECE_CONTACT_Y, "coast does not intersect piece foundations");
  assert.deepEqual([coast.position.x, coast.position.z], [3, -5]);
  assert.equal(visible.children[0].geometry, logical.geometry);
  material.dispose(); pool.release();
});

test("City preview replaces only the same owned settlement on an actual server target", () => {
  const state = { size: 58, vertices: { 7: [58, 0], 9: [0, 58], 11: [0, 0] }, occupied_v: { 7: [0, 1], 9: [1, 1] } };
  const interaction = { action: "city", targets: { vertices: [7], edges: [] }, legal: { pid: 0 }, selection: { waiting: false } };
  const building = { vertexId: 7, owner: 0, level: 1, position: toScenePosition(state.vertices[7], 58, TILE_TOP) };
  const preview = buildPreview(state, interaction, "v:7"); assert.ok(replacesSettlement(preview, building));
  assert.deepEqual(preview.building.position, building.position);
  for (const id of [9, 11, 999]) assert.equal(buildPreview(state, interaction, `v:${id}`), null);
  assert.equal(replacesSettlement(preview, { ...building, owner: 1 }), false);
  assert.equal(replacesSettlement(preview, { ...building, level: 2 }), false);
  for (const change of [{ action: null }, { selection: { waiting: true } }, { targets: { vertices: [] } }])
    assert.equal(replacesSettlement(buildPreview(state, { ...interaction, ...change }, "v:7"), building), false);
});

test("feedback follows confirmed placement/upgrade only; intent, rejection, rerender and color changes add none", () => {
  const base = { roads: [{ edge: [7, 9], owner: 0 }], buildings: [{ vertexId: 7, owner: 0, level: 1 }] };
  const previous = { key: "ROOM:1", connected: true, pieces: pieceSignatures(base) };
  for (const data of [base, { ...base, players: [{ pid: 0, color: "blue" }], pendingIntent: "city", ack: { applied: false } }])
    assert.deepEqual(confirmedPlacements(previous, pieceSignatures(data), "ROOM:1", true), []);
  const next = { roads: [...base.roads, { edge: [11, 9], owner: 1 }], buildings: [{ vertexId: 7, owner: 0, level: 2 }, { vertexId: 11, owner: 1, level: 1 }] };
  assert.deepEqual(confirmedPlacements(previous, pieceSignatures(next), "ROOM:1", true).sort(), ["e:9,11", "v:11", "v:7"]);
  assert.deepEqual(confirmedPlacements(previous, pieceSignatures({ roads: [], buildings: [] }), "ROOM:1", true), []);
});

test("initial view, reconnect, rematch and renderer remount establish a baseline without historical motion", () => {
  const current = new Map([["v:7", "0:1"]]), previous = { key: "ROOM:1", connected: true, pieces: new Map() };
  assert.equal(confirmedPlacements(null, current, "ROOM:1", true), null);
  assert.equal(confirmedPlacements(previous, current, "ROOM:2", true), null);
  assert.equal(confirmedPlacements(previous, current, "OTHER:1", true), null);
  assert.equal(confirmedPlacements(previous, current, "ROOM:1", false), null);
  assert.equal(confirmedPlacements({ ...previous, connected: false }, current, "ROOM:1", true), null);
});

test("short appearance feedback keeps contact/logical axes fixed and finishes at exact identity scale", () => {
  assert.ok(PIECE_APPEARANCE_MS <= 300);
  for (const kind of Object.keys(PIECE_ASSET_URLS)) {
    for (const t of [-1, 0, .1, .5, 1, 2]) {
      const scale = appearanceScale(kind, t); assert.ok(scale.every(value => value > 0 && value <= 1));
      if (kind === "road") assert.equal(scale[0], 1, "road endpoints do not slide during appearance");
    }
    assert.deepEqual(appearanceScale(kind, 1), [1, 1, 1]); assert.deepEqual(appearanceScale(kind, 2), [1, 1, 1]);
  }
});

test("material cleanup disposes each owned/ghost clone once and never shared source materials", () => {
  const pool = createPieceMaterials(), original = allMaterials(assets.city), sourceDisposals = [];
  original.forEach(material => material.addEventListener("dispose", () => sourceDisposals.push(material.uuid)));
  const clones = [clonePieceScene(assets.city, pool, "#ef4444", false), clonePieceScene(assets.city, pool, "#ef4444", true),
    clonePieceScene(assets.city, pool, "#3b82f6", true), clonePieceScene(assets.city, pool, "#ef4444", false)];
  const owned = [...new Set(clones.flatMap(allMaterials).filter(material => !original.includes(material)))], counts = new Map();
  owned.forEach(material => material.addEventListener("dispose", () => counts.set(material.uuid, (counts.get(material.uuid) ?? 0) + 1)));
  pool.dispose(); pool.dispose();
  assert.equal(counts.size, owned.length); assert.ok([...counts.values()].every(count => count === 1));
  assert.deepEqual(sourceDisposals, []);
});

test("Canvas lifetime preserves live PlayerColor materials through StrictMode and releases them on actual unmount", async () => {
  const pool = createVisualResources(); pool.retain();
  const original = allMaterials(assets.city).find(material => material.name === "PlayerColor");
  const material = pool.pieces.material(original, "#f2f4f8", false); let disposed = 0;
  material.addEventListener("dispose", () => disposed++);
  pool.release(); pool.retain(); await Promise.resolve();
  assert.equal(disposed, 0); assert.equal(pool.pieces.material(original, "#f2f4f8", false), material);
  pool.release(); await Promise.resolve(); assert.equal(disposed, 1);
  assert.equal(original.opacity, 1);
});
