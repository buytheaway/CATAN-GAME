import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const compiled = await build({ stdin: {
  contents: `export { clearRobberVegetation } from "./terrainReadability";
    export { cloneTerrainScene, ignoreTerrainRaycast, TERRAIN_TRANSFORM } from "./terrainAssets";
    export { threatAnchor } from "./threatMotion";
    export { Group, Mesh, BoxGeometry, MeshStandardMaterial, Raycaster, Vector3 } from "three";
    export { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";`,
  resolveDir: fileURLToPath(new URL("../src/board3d/", import.meta.url)), loader: "ts",
}, bundle: true, write: false, platform: "node", format: "esm" });
const { clearRobberVegetation, cloneTerrainScene, ignoreTerrainRaycast, TERRAIN_TRANSFORM,
  threatAnchor, Group, Mesh, BoxGeometry, MeshStandardMaterial, Raycaster, Vector3, GLTFLoader } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

const templates = new Map();
async function template(name) {
  if (!templates.has(name)) {
    const bytes = await readFile(new URL(`../public/models/terrain/${name}.glb`, import.meta.url));
    const { scene } = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "");
    templates.set(name, scene);
  }
  return templates.get(name);
}
const nodes = scene => { const result = []; scene.traverse(node => result.push(node)); return result; };
const state = scene => nodes(scene).map(node => ({ name: node.name, visible: node.visible,
  position: node.position.toArray(), quaternion: node.quaternion.toArray(), scale: node.scale.toArray() }));
const materialList = mesh => Array.isArray(mesh.material) ? mesh.material : [mesh.material];

function surfaceHeight(scene, x, z) {
  const placed = new Group(); placed.position.y = TERRAIN_TRANSFORM.lift;
  placed.rotation.y = TERRAIN_TRANSFORM.rotationY; placed.scale.setScalar(TERRAIN_TRANSFORM.scale);
  placed.add(scene); placed.updateMatrixWorld(true);
  const ray = new Raycaster(new Vector3(x, 3, z), new Vector3(0, -1, 0)), hits = [];
  for (const node of nodes(scene)) {
    if (!(node instanceof Mesh)) continue;
    let visible = true;
    for (let parent = node; parent; parent = parent.parent) visible &&= parent.visible;
    // Bypass the deliberate no-interaction raycast ONLY for this CPU geometry
    // probe; neither the production clone nor its raycast is changed.
    if (visible) Mesh.prototype.raycast.call(node, ray, hits);
  }
  placed.remove(scene);
  return Math.max(...hits.map(hit => hit.point.y));
}

test("actual Fields, Forest and Pasture reserve standing room while retaining their other vegetation", async () => {
  for (const [name, obstructing, count, remaining] of [
    ["fields", "Hex_Fields_Wheat_Mass_04", 4, "Hex_Fields_Wheat_Mass_02"],
    ["forest", "Hex_Forest_Pine_07", 3, "Hex_Forest_Pine_02"],
    ["pasture", "Hex_Pasture_Sheep_04_Standing", 2, "Hex_Pasture_Sheep_01_Alert"],
  ]) {
    const scene = cloneTerrainScene(await template(name)), before = state(scene);
    const affected = clearRobberVegetation(scene);
    assert.equal(affected.length, count, name);
    assert.equal(scene.getObjectByName(obstructing).visible, false, `${name}: the demonstrated obstructing clump is cleared`);
    assert.equal(scene.getObjectByName(remaining).visible, true, `${name}: retain distant terrain identity`);
    const removed = new Set(affected);
    const after = state(scene);
    for (let i = 0; i < before.length; i++) {
      assert.deepEqual(after[i], { ...before[i], visible: removed.has(before[i].name) ? false : before[i].visible },
        `${name}/${before[i].name}: only selected clone visibility may change`);
    }
    for (const suffix of ["Base", "Rim", "Terrain"])
      assert.equal(scene.getObjectByName(`Hex_${name[0].toUpperCase() + name.slice(1)}_${suffix}`).visible, true);
  }
});

test("real wheat and pine geometry no longer intersects the unchanged robber standing position", async () => {
  const [x, ground, z] = threatAnchor("robber", [0, 0, 0]);
  for (const name of ["fields", "forest"]) {
    const before = cloneTerrainScene(await template(name)), after = cloneTerrainScene(await template(name));
    assert(surfaceHeight(before, x, z) > ground + .25, `${name}: reproduce the existing body interpenetration`);
    clearRobberVegetation(after);
    const footprint = [[x, z], ...Array.from({ length: 8 }, (_, i) =>
      [x + Math.cos(i * Math.PI / 4) * .18, z + Math.sin(i * Math.PI / 4) * .18])];
    for (const [px, pz] of footprint)
      assert(surfaceHeight(after, px, pz) < ground, `${name}: body and footprint clear above unchanged ground`);
  }
});

test("clearance preserves cached templates, shared resources and ignored interaction raycasts", async () => {
  const source = await template("fields"), snapshot = state(source);
  const sourceMeshes = nodes(source).filter(node => node instanceof Mesh);
  const scene = cloneTerrainScene(source), other = cloneTerrainScene(source);
  const affected = clearRobberVegetation(scene), once = state(scene);
  assert.deepEqual(clearRobberVegetation(scene), affected, "idempotent affected-node identity");
  assert.deepEqual(state(scene), once, "repeated projection must not accumulate changes");
  assert.deepEqual(state(source), snapshot, "cached source stays untouched");
  assert.deepEqual(state(other), snapshot, "another hex cannot inherit the local clearance");
  const cloneMeshes = nodes(scene).filter(node => node instanceof Mesh);
  sourceMeshes.forEach((mesh, i) => {
    assert.equal(cloneMeshes[i].geometry, mesh.geometry);
    const sourceMaterials = materialList(mesh), cloneMaterials = materialList(cloneMeshes[i]);
    assert.equal(cloneMaterials.length, sourceMaterials.length);
    sourceMaterials.forEach((material, j) => assert.equal(cloneMaterials[j], material));
  });
  for (const node of nodes(scene)) assert.equal(node.raycast, ignoreTerrainRaycast);
});

test("a fresh clone restores all vegetation when the public robber/departure lifetime ends", async () => {
  const source = await template("forest"), occupied = cloneTerrainScene(source);
  const affected = clearRobberVegetation(occupied);
  assert(affected.length > 0);
  const restored = cloneTerrainScene(source);
  for (const name of affected) {
    assert.equal(occupied.getObjectByName(name).visible, false);
    assert.equal(restored.getObjectByName(name).visible, true);
  }
  assert.deepEqual(state(restored), state(source));
});

test("all other shipped terrain assets retain their complete ground and landforms", async () => {
  for (const name of ["hills", "mountains", "desert", "gold", "sea"]) {
    const scene = cloneTerrainScene(await template(name)), before = state(scene);
    assert.deepEqual(clearRobberVegetation(scene), [], name);
    assert.deepEqual(state(scene), before, name);
  }
});

test("clearance is in terrain-local space regardless of board translation, orbit or mounting scale", async () => {
  const source = await template("pasture"), detached = cloneTerrainScene(source), mounted = cloneTerrainScene(source);
  const parent = new Group(); parent.position.set(35, -4, 71); parent.rotation.set(.15, 1.2, -.2); parent.scale.set(2, 3, .7);
  parent.add(mounted);
  assert.deepEqual(clearRobberVegetation(mounted), clearRobberVegetation(detached));
  assert.deepEqual(state(mounted), state(detached), "only equivalent local nodes change, never their transforms");
});

test("unknown meshes, empty clumps and distant vegetation are safe no-ops without caching new geometry bounds", () => {
  const scene = new Group(), geometry = new BoxGeometry(.1, .1, .1), material = new MeshStandardMaterial();
  const unknown = new Mesh(geometry, material); unknown.name = "NewDecorNotApproved";
  const distant = new Mesh(geometry, material); distant.name = "Hex_Forest_Pine_99"; distant.position.set(50, 0, 50);
  const empty = new Group(); empty.name = "Hex_Fields_Wheat_Mass_99";
  scene.add(unknown, distant, empty);
  assert.equal(geometry.boundingBox, null);
  assert.deepEqual(clearRobberVegetation(scene), []);
  assert.equal(geometry.boundingBox, null, "do not populate shared mutable bounds as a side effect");
  assert(nodes(scene).every(node => node.visible));
  geometry.dispose(); material.dispose();
});
