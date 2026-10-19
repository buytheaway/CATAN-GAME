import type { Object3D } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

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
