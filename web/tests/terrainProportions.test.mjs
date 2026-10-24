import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const built = await build({ stdin: { contents: `export { applyTerrainDetail } from './terrainProportions';
  export { clearRobberVegetation } from './terrainReadability';
  export { cloneTerrainScene, TERRAIN_TRANSFORM, ignoreTerrainRaycast } from './terrainAssets';
  export { Group, Box3, Vector3, Mesh } from 'three';
  export { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';`,
  resolveDir: fileURLToPath(new URL('../src/board3d/', import.meta.url)), loader: 'ts' },
  bundle: true, write: false, platform: 'node', format: 'esm' });
const { applyTerrainDetail, clearRobberVegetation, cloneTerrainScene, TERRAIN_TRANSFORM,
  ignoreTerrainRaycast, Group, Box3, Vector3, Mesh, GLTFLoader } = await import(
  `data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);
const templates = new Map();
async function template(name) {
  if (!templates.has(name)) {
    const bytes = await readFile(new URL(`../public/models/terrain/${name}.glb`, import.meta.url));
    templates.set(name, (await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '')).scene);
  }
  return templates.get(name);
}
const nodes = scene => { const values = []; scene.traverse(node => values.push(node)); return values; };
const pose = scene => nodes(scene).map(node => ({ name: node.name, visible: node.visible,
  position: node.position.toArray(), scale: node.scale.toArray(), quaternion: node.quaternion.toArray() }));
function mount(scene) { const root = new Group(); root.position.y = TERRAIN_TRANSFORM.lift;
  root.scale.setScalar(TERRAIN_TRANSFORM.scale); root.rotation.y = TERRAIN_TRANSFORM.rotationY; root.add(scene); root.updateMatrixWorld(true); return root; }
const box = node => new Box3().setFromObject(node, true);
const near = (a, b, message) => assert(Math.abs(a - b) < 1e-6, message);
const sheep = node => /^Hex_Pasture_Sheep_\d{2}_(?:Alert|Looking_Aside|Grazing|Standing|Lamb)$/.test(node.name);
const wheat = node => /^Hex_Fields_Wheat_(?:Mass|Fringe)_\d{2}$/.test(node.name);

test('production/default and unknown profiles leave every shipped terrain unchanged', async () => {
  for (const kind of ['forest', 'fields', 'pasture', 'hills', 'mountains', 'desert', 'gold', 'sea']) {
    const scene = cloneTerrainScene(await template(kind)), before = pose(scene);
    applyTerrainDetail(scene); applyTerrainDetail(scene, 'current'); applyTerrainDetail(scene, 'unknown');
    assert.deepEqual(pose(scene), before, kind);
  }
});

test('pilot sheep shrink about their original support with unchanged footprint centre and pose', async () => {
  const scene = cloneTerrainScene(await template('pasture')); mount(scene);
  const animals = nodes(scene).filter(sheep); assert.equal(animals.length, 5);
  const before = animals.map(node => ({ bounds: box(node), quaternion: node.quaternion.toArray() }));
  applyTerrainDetail(scene, 'pilot');
  animals.forEach((node, i) => {
    const after = box(node), original = before[i].bounds, a = after.getSize(new Vector3()), b = original.getSize(new Vector3());
    for (let axis = 0; axis < 3; axis++) near(a.getComponent(axis), b.getComponent(axis) * .8, 'uniform shrink, no stretched pose');
    near(after.min.y, original.min.y, 'feet must retain actual hillside contact');
    for (const axis of ['x', 'z']) near(after.getCenter(new Vector3())[axis], original.getCenter(new Vector3())[axis], 'do not move animals into neighbours');
    assert.deepEqual(node.quaternion.toArray(), before[i].quaternion);
  });
});

test('pilot wheat retains five masses and both fringe groups, reduces height without moving footprint or ground contact', async () => {
  const scene = cloneTerrainScene(await template('fields')); mount(scene);
  const clumps = nodes(scene).filter(wheat); assert.equal(clumps.length, 9);
  const before = new Map(clumps.map(node => [node.name, box(node)]));
  applyTerrainDetail(scene, 'pilot');
  assert.equal(clumps.filter(node => node.visible && node.name.includes('Mass')).length, 5);
  assert.equal(clumps.filter(node => node.visible && node.name.includes('Fringe')).length, 2);
  for (const node of clumps.filter(node => node.visible)) {
    const after = box(node), original = before.get(node.name);
    near(after.getSize(new Vector3()).y, original.getSize(new Vector3()).y * .78);
    near(after.min.y, original.min.y);
    for (const axis of ['x', 'z']) { near(after.min[axis], original.min[axis]); near(after.max[axis], original.max[axis]); }
  }
});

test('only two approved decoration families change; cached assets, shared resources and ignored raycasts survive', async () => {
  for (const kind of ['fields', 'pasture', 'forest', 'hills', 'mountains', 'desert', 'gold', 'sea']) {
    const source = await template(kind), unchanged = pose(source), scene = cloneTerrainScene(source), other = cloneTerrainScene(source);
    const before = pose(scene), originals = nodes(source), clones = nodes(scene);
    applyTerrainDetail(scene, 'pilot');
    clones.forEach((node, i) => {
      if (!(sheep(node) || wheat(node))) assert.deepEqual(pose(node)[0], before[i], 'no broad landform or piece transform');
      if (node instanceof Mesh) { assert.equal(node.geometry, originals[i].geometry); assert.equal(node.material, originals[i].material); }
      assert.equal(node.raycast, ignoreTerrainRaycast);
    });
    assert.deepEqual(pose(source), unchanged); assert.deepEqual(pose(other), unchanged);
  }
});

test('pilot never resurrects 5E.1 clearance, is idempotent and restores via a fresh current clone', async () => {
  for (const kind of ['fields', 'pasture', 'forest']) {
    const source = await template(kind), scene = cloneTerrainScene(source), cleared = clearRobberVegetation(scene);
    applyTerrainDetail(scene, 'pilot'); const once = pose(scene);
    for (const name of cleared) assert.equal(scene.getObjectByName(name).visible, false, 'existing standing area stays clear');
    applyTerrainDetail(scene, 'pilot'); assert.deepEqual(pose(scene), once, 'do not compound on repeated projection');
    const restored = cloneTerrainScene(source); applyTerrainDetail(restored, 'current');
    assert.deepEqual(pose(restored), pose(source), 'no cross-tile or preference history');
  }
});
