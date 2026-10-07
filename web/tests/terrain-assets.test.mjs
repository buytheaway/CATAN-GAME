import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const compiled = await build({
  stdin: {
    contents: 'export * from "./terrainAssets"; export { Group, Mesh, BoxGeometry, MeshStandardMaterial, Box3 } from "three"; export { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";',
    resolveDir: fileURLToPath(new URL("../src/board3d/", import.meta.url)), loader: "ts",
  },
  bundle: true, write: false, platform: "node", format: "esm",
});
const { TERRAIN_ASSET_URLS, TERRAIN_TRANSFORM, terrainAssetName, createTerrainAssetCache,
  cloneTerrainScene, ignoreTerrainRaycast, Group, Mesh, BoxGeometry, MeshStandardMaterial, Box3, GLTFLoader } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

test("canonical snapshot terrains and resource aliases select the same eight assets", () => {
  assert.equal(Object.keys(TERRAIN_ASSET_URLS).length, 8);
  for (const name of ["forest", "fields", "pasture", "hills", "mountains", "desert", "sea", "gold"]) {
    assert.equal(terrainAssetName(name), name);
    assert.equal(TERRAIN_ASSET_URLS[name], `/models/terrain/${name}.glb`);
  }
  for (const [alias, name] of Object.entries({ wood: "forest", wheat: "fields", sheep: "pasture",
    clay: "hills", brick: "hills", ore: "mountains" })) assert.equal(terrainAssetName(alias), name);
});

test("unknown terrains use fallback without requesting an invented asset", async () => {
  const cache = createTerrainAssetCache(() => assert.fail("unknown terrain must not load"));
  for (const name of ["", "ocean_background", "unknown", "toString", "__proto__"]) {
    assert.equal(terrainAssetName(name), null);
    assert.equal(await cache(name), null);
  }
});

test("concurrent hexes and later mounts share a single load, including aliases", async () => {
  const calls = []; let complete;
  const cache = createTerrainAssetCache(url => {
    calls.push(url);
    return new Promise(resolve => { complete = resolve; });
  });
  const requests = Array.from({ length: 19 }, () => cache("forest"));
  assert.equal(cache("wood"), requests[0]);
  await Promise.resolve();
  assert.deepEqual(calls, ["/models/terrain/forest.glb"]);
  const template = new Group(); complete(template);
  assert.ok((await Promise.all(requests)).every(scene => scene === template));
  assert.equal(await cache("forest"), template);
  assert.equal(calls.length, 1);
});

test("failed or synchronously throwing loaders keep a local fallback and warn once", async () => {
  for (const load of [() => Promise.reject(new Error("404")), () => { throw new Error("loader error"); }]) {
    const warnings = [], loaded = [];
    const cache = createTerrainAssetCache(url => {
      loaded.push(url);
      return url.endsWith("sea.glb") ? load() : Promise.resolve(new Group());
    }, message => warnings.push(message));
    assert.deepEqual(await Promise.all([cache("sea"), cache("sea"), cache("sea")]), [null, null, null]);
    assert.equal(await cache("sea"), null);
    assert.ok(await cache("gold")); // A missing terrain cannot break unrelated assets.
    assert.deepEqual(loaded, ["/models/terrain/sea.glb", "/models/terrain/gold.glb"]);
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /sea\.glb.*fallback/);
  }
});

test("hex clones own their nodes, share immutable resources, and never raycast", () => {
  const template = new Group(), geometry = new BoxGeometry(), material = new MeshStandardMaterial();
  const mesh = new Mesh(geometry, material); template.add(mesh);
  const sourceRaycast = mesh.raycast;
  const a = cloneTerrainScene(template), b = cloneTerrainScene(template);
  assert.notEqual(a, b); assert.notEqual(a.children[0], b.children[0]);
  assert.equal(a.children[0].geometry, geometry); assert.equal(b.children[0].material, material);
  a.position.x = 12; a.children[0].position.y = 3;
  assert.equal(template.position.x, 0); assert.equal(b.children[0].position.y, 0);
  assert.equal(mesh.raycast, sourceRaycast); assert.equal(mesh.castShadow, false);
  for (const clone of [a, b]) {
    clone.traverse(node => assert.equal(node.raycast, ignoreTerrainRaycast));
    assert.ok(clone.children[0].castShadow && clone.children[0].receiveShadow);
  }
  geometry.dispose(); material.dispose();
});

test("all shipped GLB bases use one transform, align with pointy-top hexes and rest at Y=0", async () => {
  assert.equal(TERRAIN_TRANSFORM.scale, 1 / 1.2);
  assert.equal(TERRAIN_TRANSFORM.rotationY, Math.PI / 2);
  assert.equal(TERRAIN_TRANSFORM.lift, TERRAIN_TRANSFORM.sourceLift * TERRAIN_TRANSFORM.scale);
  let reference;
  for (const name of Object.keys(TERRAIN_ASSET_URLS)) {
    const bytes = await readFile(new URL(`../public/models/terrain/${name}.glb`, import.meta.url));
    const data = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    const { scene } = await new GLTFLoader().parseAsync(data, "");
    const placed = new Group(); placed.position.y = TERRAIN_TRANSFORM.lift;
    placed.rotation.y = TERRAIN_TRANSFORM.rotationY; placed.scale.setScalar(TERRAIN_TRANSFORM.scale);
    placed.add(scene); placed.updateMatrixWorld(true);
    const base = scene.getObjectByName(`Hex_${name[0].toUpperCase() + name.slice(1)}_Base`);
    assert.ok(base, `${name}: wooden base is present`);
    const box = new Box3().setFromObject(base);
    const bounds = [...box.min.toArray(), ...box.max.toArray()];
    assert.ok(Math.abs(box.min.y) < 1e-6, `${name}: common bottom correction`);
    assert.ok(Math.abs(box.max.x - Math.sqrt(3) / 2) < 1e-6, `${name}: shared board edge spacing`);
    assert.ok(box.max.z > .99 && box.max.z <= 1, `${name}: pointy-top radius`);
    assert.ok(Math.abs(box.min.x + box.max.x) < 1e-6 && Math.abs(box.min.z + box.max.z) < 1e-6);
    if (reference) bounds.forEach((value, i) => assert.ok(Math.abs(value - reference[i]) < 1e-6));
    else reference = bounds;
    scene.traverse(node => { if (node.isMesh) node.geometry.dispose(); });
  }
});
