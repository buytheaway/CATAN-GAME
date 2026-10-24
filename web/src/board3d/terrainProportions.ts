import { Box3, Matrix4, Mesh, Vector3, type Object3D } from "three";

export type TerrainDetail = "current" | "pilot";
const applied = new WeakSet<Object3D>();
const sheep = /^Hex_Pasture_Sheep_\d{2}_(?:Alert|Looking_Aside|Grazing|Standing|Lamb)$/;
const wheat = /^Hex_Fields_Wheat_(?:Mass|Fringe)_\d{2}$/;
const sparseWheat = new Set(["Hex_Fields_Wheat_Mass_02", "Hex_Fields_Wheat_Mass_07"]);

/** Exact support/centre in the node's parent space; no shared bounds are written. */
function support(node: Object3D) {
  const inverse = node.parent?.matrixWorld.clone().invert() ?? new Matrix4();
  const bounds = new Box3(), point = new Vector3(), transform = new Matrix4();
  node.traverse(child => {
    if (!(child instanceof Mesh)) return;
    const positions = child.geometry.getAttribute("position");
    if (!positions) return;
    transform.multiplyMatrices(inverse, child.matrixWorld);
    for (let i = 0; i < positions.count; i++) {
      point.set(positions.getX(i), positions.getY(i), positions.getZ(i)).applyMatrix4(transform);
      bounds.expandByPoint(point);
    }
  });
  if (bounds.isEmpty()) return null;
  const anchor = bounds.getCenter(new Vector3());
  anchor.y = bounds.min.y;
  return anchor;
}

/**
 * Opt-in presentation experiment on a fresh owned clone, AFTER 5E.1 clearance.
 * Production defaults to current. Geometry/materials, ground, IDs and pieces
 * are untouched. Shrinking about each support point avoids floating animals.
 */
export function applyTerrainDetail(scene: Object3D, detail: TerrainDetail = "current") {
  if (detail !== "pilot" || applied.has(scene)) return;
  applied.add(scene);
  scene.updateWorldMatrix(true, true);
  scene.traverse(node => {
    if (!node.visible || !(sheep.test(node.name) || wheat.test(node.name))) return;
    if (sparseWheat.has(node.name)) { node.visible = false; return; }
    const anchor = support(node);
    if (!anchor) return;
    const scale = sheep.test(node.name) ? new Vector3(.8, .8, .8) : new Vector3(1, .78, 1);
    node.position.sub(anchor).multiply(scale).add(anchor);
    node.scale.multiply(scale);
    node.updateWorldMatrix(false, true);
  });
}
