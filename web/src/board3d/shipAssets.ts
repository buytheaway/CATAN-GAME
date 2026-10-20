import { DoubleSide, Mesh, type Object3D } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clonePieceScene, type createPieceMaterials } from "./pieceAssets";

export type ShipModel = "procedural" | "glb";
export const SHIP_ASSET_URL = "/models/pieces/ship-pilot.glb";

/** The source uses local X as its heading; preserve the existing edge-length fit. */
export function shipAssetScale(length: number): [number, number, number] {
  return [length * .88, 1, 1];
}

/** One immutable template per page, including a cached procedural fallback on failure. */
export function createShipAssetCache(
  load: (url: string) => Promise<Object3D> = url => new GLTFLoader().loadAsync(url).then(gltf => gltf.scene),
  warn: (message: string) => void = message => console.warn(message),
) {
  let pending: Promise<Object3D | null> | undefined;
  return () => pending ??= Promise.resolve().then(() => load(SHIP_ASSET_URL)).catch(() => {
    warn(`[Board3D] Could not load ${SHIP_ASSET_URL}; using procedural ship fallback.`);
    return null;
  });
}

export const loadShipAsset = createShipAssetCache();

/** Preserve the established two-sided transparent hover/echo appearance. */
export function cloneShipScene(template: Object3D, pool: ReturnType<typeof createPieceMaterials>, color: string, ghost: boolean) {
  const scene = clonePieceScene(template, pool, color, ghost);
  if (ghost) scene.traverse(node => {
    if (node instanceof Mesh) for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
      // These are Canvas-owned ghost copies, never cached neutral originals.
      material.side = DoubleSide;
    }
  });
  return scene;
}
