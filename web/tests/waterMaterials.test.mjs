import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const built = await build({ stdin: { contents: `export * from './waterMaterials';
  export { createVisualResources } from './resources';
  export { cloneTerrainScene } from './terrainAssets';
  export { MeshStandardMaterial, MeshBasicMaterial } from 'three';
  export { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';`,
  resolveDir: fileURLToPath(new URL('../src/board3d/', import.meta.url)), loader: 'ts' },
  bundle: true, write: false, platform: 'node', format: 'esm' });
const { createWaterMaterialCache, waterStyle, SEA_WATER_PILOT, SEA_WATER_ROUGHNESS,
  createVisualResources, cloneTerrainScene, MeshStandardMaterial, MeshBasicMaterial, GLTFLoader } = await import(
  `data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);
const bytes = await readFile(new URL('../public/models/terrain/sea.glb', import.meta.url));
const source = (await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '')).scene;
const meshes = scene => { const result = []; scene.traverse(n => { if (n.isMesh) result.push(n); }); return result; };
const materials = scene => new Set(meshes(scene).flatMap(n => Array.isArray(n.material) ? n.material : [n.material]));

test('current is the default, unknown presets fall back, and material candidates exclude wood/unknown types', () => {
  assert.equal(waterStyle(), waterStyle('current')); assert.equal(waterStyle('unsupported'), waterStyle());
  assert.notEqual(waterStyle('pilot'), waterStyle());
  const cache = createWaterMaterialCache();
  for (const m of [new MeshStandardMaterial(), new MeshBasicMaterial(), ...materials(source)]) {
    if (m.type === 'MeshPhysicalMaterial' && Object.hasOwn(SEA_WATER_PILOT, m.name)) continue;
    assert.equal(cache.get(m), m, m.name);
  }
  cache.dispose();
});

test('real sea GLB pilot changes exactly nine water materials and preserves all other physical properties', () => {
  const cache = createWaterMaterialCache(), before = new Map([...materials(source)].map(m => [m, m.toJSON()]));
  let count = 0;
  for (const m of materials(source)) {
    const owned = cache.get(m);
    if (!Object.hasOwn(SEA_WATER_PILOT, m.name)) { assert.equal(owned, m); continue; }
    count++; assert.notEqual(owned, m); assert.equal(owned.type, m.type);
    assert.equal('#' + owned.color.getHexString(), SEA_WATER_PILOT[m.name]);
    assert.equal(owned.roughness, SEA_WATER_ROUGHNESS);
    const a = owned.toJSON(), b = m.toJSON();
    for (const key of ['uuid', 'color', 'roughness']) { delete a[key]; delete b[key]; }
    assert.deepEqual(a, b, 'side/depth/alpha/specular/maps/shader features must not change');
  }
  assert.equal(count, 9);
  for (const [m, json] of before) assert.deepEqual(m.toJSON(), json, 'immutable source material');
  cache.dispose();
});

test('many owned sea clones share bounded pilot materials without changing geometry, transforms, IDs or another clone', () => {
  const cache = createWaterMaterialCache(), original = meshes(source), untouched = cloneTerrainScene(source), seen = new Set();
  for (let tile = 0; tile < 50; tile++) {
    const scene = cloneTerrainScene(source);
    meshes(scene).forEach((n, i) => {
      const matrix = n.matrix.toArray(), raycast = n.raycast, data = { ...n.userData };
      n.material = Array.isArray(n.material) ? n.material.map(m => cache.get(m)) : cache.get(n.material);
      assert.equal(n.geometry, original[i].geometry); assert.deepEqual(n.matrix.toArray(), matrix);
      assert.equal(n.raycast, raycast); assert.deepEqual(n.userData, data);
      for (const m of Array.isArray(n.material) ? n.material : [n.material]) seen.add(m);
    });
  }
  assert.equal(seen.size, materials(source).size);
  meshes(untouched).forEach((n, i) => assert.equal(n.material, original[i].material));
  cache.dispose();
});

test('scene pool owns/disposes pilot materials once, respects StrictMode leases and never disposes cached GLB sources', async () => {
  const pool = createVisualResources(), original = [...materials(source)], disposal = new Map();
  const owned = new Set(original.map(m => pool.waterMaterial(m)));
  for (const m of new Set([...original, ...owned])) m.addEventListener('dispose', () => disposal.set(m, (disposal.get(m) || 0) + 1));
  pool.retain(); pool.release(); pool.retain(); await Promise.resolve();
  assert.equal(disposal.size, 0, 'immediate StrictMode remount keeps live resources');
  original.forEach(m => assert.equal(pool.waterMaterial(m), pool.waterMaterial(m), 'reuse across preset switches'));
  pool.release(); await Promise.resolve();
  for (const m of original) assert.equal(disposal.get(m) || 0, 0, 'source survives scene unmount');
  for (const m of owned) if (!original.includes(m)) assert.equal(disposal.get(m), 1);
});
