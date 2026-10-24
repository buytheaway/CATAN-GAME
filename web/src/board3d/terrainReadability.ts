import { Box3, Matrix4, Mesh, Quaternion, Vector3, type Object3D } from "three";
import { TERRAIN_TRANSFORM } from "./terrainAssets";
import { threatAnchor } from "./threatMotion";

// Only demonstrated, separable vegetation families. Never remove the terrain,
// base, rim or broad landforms to make room for a figure.
const vegetation = /^Hex_(?:Fields_Wheat_(?:Mass|Fringe)_\d{2}|Forest_Pine_\d{2}|Pasture_Sheep_\d{2}_(?:Alert|Looking_Aside|Grazing|Standing|Lamb))$/;
const clearanceRadius = .34;

/**
 * Reserve a small standing area on an OWNED clone of a revealed robber tile.
 * The caller owns public occupancy/visibility and finite departure lifetimes.
 * Geometry, materials, transforms and the cached source are never changed.
 */
export function clearRobberVegetation(scene: Object3D): readonly string[] {
  scene.updateWorldMatrix(true, true);
  const terrainFromWorld = new Matrix4().compose(
    new Vector3(0, TERRAIN_TRANSFORM.lift, 0),
    new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), TERRAIN_TRANSFORM.rotationY),
    new Vector3().setScalar(TERRAIN_TRANSFORM.scale),
  ).multiply(scene.matrixWorld.clone().invert());
  const [x, , z] = threatAnchor("robber", [0, 0, 0]);
  const hidden: string[] = [];
  scene.traverse(node => {
    if (!vegetation.test(node.name)) return;
    const bounds = new Box3();
    node.traverse(child => {
      if (!(child instanceof Mesh)) return;
      const geometry = child.geometry;
      // GLTFLoader supplies bounds; the fallback must not populate or otherwise
      // mutate a shared BufferGeometry when a synthetic mesh has no cached box.
      let box = geometry.boundingBox?.clone();
      if (!box) {
        const positions = geometry.getAttribute("position");
        if (!positions) return;
        box = new Box3();
        const point = new Vector3();
        for (let i = 0; i < positions.count; i++)
          box.expandByPoint(point.set(positions.getX(i), positions.getY(i), positions.getZ(i)));
      }
      bounds.union(box.applyMatrix4(new Matrix4().multiplyMatrices(terrainFromWorld, child.matrixWorld)));
    });
    if (bounds.isEmpty()) return;
    const dx = Math.max(bounds.min.x - x, 0, x - bounds.max.x);
    const dz = Math.max(bounds.min.z - z, 0, z - bounds.max.z);
    if (Math.hypot(dx, dz) < clearanceRadius) {
      node.visible = false;
      hidden.push(node.name);
    }
  });
  return hidden;
}
