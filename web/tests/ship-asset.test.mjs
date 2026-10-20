import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { createHash } from "node:crypto";

const compiled = await build({
  stdin: { contents: `export * from "./shipAssets"; export * from "./pieceAssets";
    export * from "./coordinates"; export * from "./shipMotion"; export { ROOM_COLORS } from "../board/colors";
    export { Group, Mesh, BoxGeometry, MeshStandardMaterial, Vector3, Raycaster, Box3, FrontSide, DoubleSide } from "three";
    export { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";`,
    resolveDir: fileURLToPath(new URL("../src/board3d/", import.meta.url)), loader: "ts" },
  bundle: true, write: false, platform: "node", format: "esm",
});
const { SHIP_ASSET_URL, createShipAssetCache, shipAssetScale, cloneShipScene, createPieceMaterials,
  clonePieceScene, ignorePieceRaycast, edgePlacement, ROOM_COLORS,
  shipPose, shipDeparture, Group, Mesh, BoxGeometry, MeshStandardMaterial, Vector3, Raycaster, Box3, GLTFLoader, FrontSide, DoubleSide } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

function template() {
  const source = new Group();
  for (const name of ["PlayerColor", "HullWood", "CanvasIvory"]) {
    const material = new MeshStandardMaterial({ color: name === "PlayerColor" ? "#ef4444" : "#d8bd89" });
    material.name = name;
    source.add(new Mesh(new BoxGeometry(.8, .5, .28), material));
  }
  return source;
}
const meshes = scene => { const result = []; scene.traverse(node => { if (node.isMesh) result.push(node); }); return result; };
const bytes = await readFile(new URL("../public/models/pieces/ship-pilot.glb", import.meta.url));
const asset = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "");
const manifest = JSON.parse(await readFile(new URL("../../docs/design/references/blender/ship-pilot.json", import.meta.url), "utf8"));
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);

test("ship manifest describes actual bytes, triangles, named selective culling and validated export", () => {
  assert.equal(manifest.glb_sha256, createHash("sha256").update(bytes).digest("hex"));
  assert.equal(manifest.glb_bytes, bytes.length);
  assert.equal(manifest.triangles, meshes(asset.scene).reduce((sum, m) => sum + m.geometry.index.count / 3, 0));
  assert.deepEqual(manifest.culling, { HullWood: "FrontSide", PlayerColor: "FrontSide", CanvasIvory: "DoubleSide" });
  assert.equal(manifest.glb_reload_verified, true);
  for (const mesh of meshes(asset.scene)) assert.equal(mesh.material.side, mesh.material.name === "CanvasIvory" ? DoubleSide : FrontSide);
});

// Independent verification of exported triangles, including normal splits at the
// same position. This never edits/welds the rendering geometry.
function topology(geometry) {
  const p = geometry.attributes.position, normal = geometry.attributes.normal;
  const keys = new Map(), ids = [], triangles = [], edges = new Map();
  for (let i = 0; i < p.count; i++) {
    const key = [p.getX(i), p.getY(i), p.getZ(i)].map(v => v.toFixed(6)).join(",");
    if (!keys.has(key)) keys.set(key, keys.size); ids.push(keys.get(key));
  }
  for (let i = 0; i < geometry.index.count; i += 3) {
    const vertices = [0, 1, 2].map(j => geometry.index.getX(i + j)), welded = vertices.map(v => ids[v]);
    const points = vertices.map(v => new Vector3().fromBufferAttribute(p, v));
    const faceNormal = points[1].clone().sub(points[0]).cross(points[2].clone().sub(points[0]));
    assert.ok(faceNormal.length() > 1e-12, "degenerate triangle");
    for (const vertex of vertices) assert.ok(faceNormal.clone().normalize().dot(new Vector3().fromBufferAttribute(normal, vertex)) > .5, "normal opposes face winding");
    const face = triangles.length; triangles.push({ points, neighbors: new Set(), closed: true });
    for (let j = 0; j < 3; j++) {
      const a = welded[j], b = welded[(j + 1) % 3], key = [a, b].sort((a, b) => a - b).join(",");
      if (!edges.has(key)) edges.set(key, []); edges.get(key).push({ face, a, b });
    }
  }
  let boundary = 0;
  for (const uses of edges.values()) {
    assert.ok(uses.length <= 2, "non-manifold shared edge");
    if (uses.length === 1) { boundary++; triangles[uses[0].face].closed = false; }
    else {
      const [a, b] = uses; assert.equal(a.a, b.b, "inconsistent edge winding"); assert.equal(a.b, b.a);
      triangles[a.face].neighbors.add(b.face); triangles[b.face].neighbors.add(a.face);
    }
  }
  const unseen = new Set(triangles.map((_, i) => i)), volumes = [];
  while (unseen.size) {
    const pending = [unseen.values().next().value], component = [];
    while (pending.length) { const i = pending.pop(); if (!unseen.delete(i)) continue;
      component.push(triangles[i]); pending.push(...triangles[i].neighbors); }
    if (component.every(t => t.closed)) volumes.push(component.reduce((sum, t) => sum + t.points[0].dot(t.points[1].clone().cross(t.points[2])) / 6, 0));
  }
  return { boundary, volumes };
}
test("exported closed ship components face outward; only the intentional deck overlay stays open", () => {
  for (const mesh of meshes(asset.scene)) {
    const info = topology(mesh.geometry);
    assert.equal(info.boundary, mesh.material.name === "HullWood" ? 7 : 0);
    assert.ok(info.volumes.length > 0 && info.volumes.every(v => v > 1e-10), "inward closed component");
  }
});
test("selective ship culling survives owner/transparent ghost cloning without changing shared sources", () => {
  const pool = createPieceMaterials();
  for (const ghost of [false, true]) for (const color of Object.values(ROOM_COLORS)) {
    const clone = cloneShipScene(asset.scene, pool, color, ghost);
    for (const part of meshes(clone)) {
      assert.equal(part.material.side, ghost || part.material.name === "CanvasIvory" ? DoubleSide : FrontSide);
      assert.equal(part.material.transparent, ghost); assert.equal(part.castShadow, !ghost);
      assert.equal(part.raycast, ignorePieceRaycast);
    }
  }
  assert.ok(meshes(asset.scene).every(p => !p.material.transparent && p.material.side === (p.material.name === "CanvasIvory" ? DoubleSide : FrontSide))); pool.dispose();
});

test("experimental ship cache shares one pending request and immutable source across later mounts", async () => {
  const calls = []; let finish;
  const cache = createShipAssetCache(url => { calls.push(url); return new Promise(resolve => { finish = resolve; }); });
  assert.deepEqual(calls, []);
  const requests = Array.from({ length: 24 }, () => cache());
  assert.ok(requests.every(request => request === requests[0]));
  await Promise.resolve(); assert.deepEqual(calls, [SHIP_ASSET_URL]);
  assert.equal(SHIP_ASSET_URL, "/models/pieces/ship-pilot.glb");
  const source = template(); finish(source);
  assert.ok((await Promise.all(requests)).every(scene => scene === source));
  assert.equal(await cache(), source); assert.equal(calls.length, 1);
});

test("missing or invalid GLB retains a cached local procedural fallback without a rejection loop", async () => {
  for (const failure of [() => Promise.reject(new Error("404")), () => { throw new Error("invalid GLB"); }]) {
    const warnings = [], calls = [];
    const cache = createShipAssetCache(url => { calls.push(url); return failure(); }, warning => warnings.push(warning));
    assert.deepEqual(await Promise.all([cache(), cache()]), [null, null]);
    assert.equal(await cache(), null); assert.equal(calls.length, 1); assert.equal(warnings.length, 1);
    assert.match(warnings[0], /ship-pilot\.glb.*procedural ship fallback/);
  }
});

test("ship asset scales only local X while original edge anchors and heading stay authoritative", () => {
  for (const [a, b] of [[[2, 0, -1], [5, 0, 1]], [[5, 0, 1], [2, 0, -1]], [[0, 0, 0], [0, 0, 2]]]) {
    const placement = edgePlacement(a, b), anchor = new Group(), asset = new Group();
    anchor.position.set(...placement.position); anchor.rotation.y = placement.rotation;
    asset.scale.set(...shipAssetScale(placement.length)); anchor.add(asset); anchor.updateMatrixWorld(true);
    const start = new Vector3(-.4, 0, 0).applyMatrix4(asset.matrixWorld);
    const end = new Vector3(.4, 0, 0).applyMatrix4(asset.matrixWorld);
    assert.deepEqual(asset.scale.toArray(), [placement.length * .88, 1, 1]);
    const direction = end.clone().sub(start).normalize();
    assert.ok(Math.abs(direction.x - (b[0] - a[0]) / placement.length) < 1e-8);
    assert.ok(Math.abs(direction.z - (b[2] - a[2]) / placement.length) < 1e-8);
    assert.deepEqual(anchor.position.toArray(), placement.position); assert.equal(anchor.rotation.y, placement.rotation);
    assert.ok(Math.abs(start.distanceTo(end) - placement.length * .8 * .88) < 1e-8);
  }
});

test("all six owner colors recolor PlayerColor only and leave cached ship and neutral materials intact", () => {
  const source = template(), pool = createPieceMaterials(), original = meshes(source);
  for (const color of Object.values(ROOM_COLORS)) {
    const clone = clonePieceScene(source, pool, color, false), parts = meshes(clone);
    assert.equal(parts[0].material.color.getHexString(), color.slice(1));
    assert.notEqual(parts[0].material, original[0].material);
    assert.equal(parts[1].material, original[1].material); assert.equal(parts[2].material, original[2].material);
    parts.forEach((mesh, i) => assert.equal(mesh.geometry, original[i].geometry));
    assert.equal(original[0].material.color.getHexString(), "ef4444");
  }
  pool.dispose();
});

test("ship hover/source-echo clones keep isolated ghost materials and cannot intercept a legal target", () => {
  const source = template(), pool = createPieceMaterials();
  const placed = clonePieceScene(source, pool, "#ef4444", false), ghost = clonePieceScene(source, pool, "#3b82f6", true);
  const ray = new Raycaster(new Vector3(0, 2, 0), new Vector3(0, -1, 0));
  source.updateMatrixWorld(true); placed.updateMatrixWorld(true); ghost.updateMatrixWorld(true);
  assert.ok(ray.intersectObject(source, true).length);
  for (const clone of [placed, ghost]) {
    clone.traverse(node => assert.equal(node.raycast, ignorePieceRaycast));
    assert.deepEqual(ray.intersectObject(clone, true), []);
  }
  meshes(ghost).forEach((mesh, i) => {
    assert.equal(mesh.material.opacity, .46); assert.equal(mesh.material.depthWrite, false);
    assert.equal(mesh.material.depthTest, false); assert.equal(mesh.castShadow, false);
    assert.equal(meshes(placed)[i].material.opacity, 1); assert.equal(meshes(source)[i].material.opacity, 1);
  });
  assert.equal(meshes(ghost)[0].material.color.getHexString(), "3b82f6");
  pool.dispose();
});

test("Canvas-owned ship color/ghost cleanup never disposes the cached model geometry or source materials", () => {
  const source = template(), pool = createPieceMaterials(), sourceDisposals = [], counts = new Map();
  meshes(source).forEach(mesh => {
    mesh.geometry.addEventListener("dispose", () => sourceDisposals.push("geometry"));
    mesh.material.addEventListener("dispose", () => sourceDisposals.push("material"));
  });
  const instances = [clonePieceScene(source, pool, "#ef4444", false), clonePieceScene(source, pool, "#ef4444", true)];
  const originals = meshes(source).map(mesh => mesh.material);
  const owned = new Set(instances.flatMap(meshes).map(mesh => mesh.material).filter(material => !originals.includes(material)));
  owned.forEach(material => material.addEventListener("dispose", () => counts.set(material.uuid, (counts.get(material.uuid) ?? 0) + 1)));
  pool.dispose(); pool.dispose();
  assert.equal(counts.size, owned.size); assert.ok([...counts.values()].every(count => count === 1));
  assert.deepEqual(sourceDisposals, []);
});

test("exported Blender pilot is a compact self-contained static X-heading ship with a grounded centered pivot", () => {
  const jsonSize = bytes.readUInt32LE(12), gltf = JSON.parse(bytes.subarray(20, 20 + jsonSize).toString("utf8"));
  assert.ok(bytes.length <= 24 * 1024, "pilot must stay within its small transfer budget");
  assert.equal(gltf.images?.length ?? 0, 0); assert.equal(gltf.textures?.length ?? 0, 0);
  assert.ok(gltf.buffers.every(buffer => !buffer.uri), "no external resources");
  assert.equal(asset.animations.length, 0); assert.equal(gltf.skins?.length ?? 0, 0);
  const parts = meshes(asset.scene), materials = parts.map(mesh => mesh.material);
  assert.equal(parts.length, 3);
  assert.deepEqual(materials.map(material => material.name).sort(), ["CanvasIvory", "HullWood", "PlayerColor"]);
  assert.ok(materials.every(material => material.isMeshStandardMaterial && !material.transparent));
  const triangles = parts.reduce((count, mesh) => count + (mesh.geometry.index?.count ?? mesh.geometry.attributes.position.count) / 3, 0);
  assert.ok(triangles <= 256, `pilot triangle budget exceeded: ${triangles}`);
  const bounds = new Box3().setFromObject(asset.scene), size = bounds.getSize(new Vector3());
  close(bounds.min.y, 0); close(bounds.min.x + bounds.max.x, 0); close(bounds.min.z + bounds.max.z, 0);
  close(size.x, .8); assert.ok(size.y >= .45 && size.y <= .56); assert.ok(size.z <= .3);
});

test("real pilot clones preserve owner/ghost isolation, ignored raycasts and existing finite ship motion endpoints", () => {
  const pool = createPieceMaterials(), sourceParts = meshes(asset.scene);
  const before = sourceParts.map(mesh => ({ color: mesh.material.color.getHex(), opacity: mesh.material.opacity }));
  for (const color of Object.values(ROOM_COLORS)) {
    const placed = clonePieceScene(asset.scene, pool, color, false), ghost = clonePieceScene(asset.scene, pool, color, true);
    for (const clone of [placed, ghost]) {
      meshes(clone).forEach((mesh, i) => {
        assert.equal(mesh.geometry, sourceParts[i].geometry); assert.equal(mesh.raycast, ignorePieceRaycast);
        if (mesh.material.name === "PlayerColor") assert.equal(mesh.material.color.getHexString(), color.slice(1));
        else assert.equal(mesh.material.color.getHex(), sourceParts[i].material.color.getHex());
      });
      clone.updateMatrixWorld(true);
      assert.deepEqual(new Raycaster(new Vector3(0, 2, 0), new Vector3(0, -1, 0)).intersectObject(clone, true), []);
    }
    meshes(ghost).forEach(mesh => assert.equal(mesh.material.opacity, .46));
    const outer = new Group(), motion = new Group(), scaled = new Group();
    outer.position.set(3, .32, -2); outer.rotation.y = .7;
    scaled.scale.set(...shipAssetScale(1.3)); scaled.add(placed); motion.add(scaled); outer.add(motion);
    for (const kind of ["build", "move"]) {
      const pose = shipPose([7, 9], 0, { kind, owner: 0, started: 100 }, 1100, true);
      motion.position.y = pose.y; motion.rotation.set(pose.pitch, 0, pose.roll); motion.scale.set(...pose.scale);
      assert.equal(pose.active, false); assert.deepEqual(pose.scale, [1, 1, 1]);
      assert.deepEqual(outer.position.toArray(), [3, .32, -2]); assert.equal(outer.rotation.y, .7);
      assert.deepEqual(pose, shipPose([7, 9], 0, undefined, 1100, true), "completion returns to the existing idle pose");
    }
    const still = shipPose([7, 9], 5, { kind: "move", owner: 0, started: 100 }, 200, false);
    assert.deepEqual(still.scale, [1, 1, 1]); assert.equal(still.y, 0); assert.equal(still.active, false);
    assert.equal(shipDeparture(100, 500).visible, false);
  }
  assert.deepEqual(sourceParts.map(mesh => ({ color: mesh.material.color.getHex(), opacity: mesh.material.opacity })), before);
  pool.dispose();
});
