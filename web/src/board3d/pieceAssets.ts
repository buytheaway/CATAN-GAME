import { Material, Mesh, MeshStandardMaterial, type Object3D } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { BOARD_RIM_TOP, TILE_TOP } from "./coordinates";

export const PIECE_ASSET_URLS = {
  settlement: "/models/pieces/settlement.glb",
  city: "/models/pieces/city.glb",
  road: "/models/pieces/road.glb",
} as const;
export type PieceKind = keyof typeof PIECE_ASSET_URLS;

// All finalized terrain GLBs share this rim top after their existing transform.
// Piece sources already contact Y=0; neither their nodes nor the game anchors move.
export { BOARD_RIM_TOP as PIECE_CONTACT_Y } from "./coordinates";
export function pieceOffset(kind: PieceKind): [number, number, number] {
  return [0, BOARD_RIM_TOP - TILE_TOP - (kind === "road" ? .06 : 0), 0];
}
export const ignorePieceRaycast = () => undefined;

export function createPieceAssetCache(
  load: (url: string) => Promise<Object3D> = url => new GLTFLoader().loadAsync(url).then(gltf => gltf.scene),
  warn: (message: string) => void = message => console.warn(message),
) {
  const cache = new Map<PieceKind, Promise<Object3D | null>>();
  return (kind: PieceKind): Promise<Object3D | null> => {
    if (!cache.has(kind)) cache.set(kind, Promise.resolve().then(() => load(PIECE_ASSET_URLS[kind])).catch(() => {
      warn(`[Board3D] Could not load ${PIECE_ASSET_URLS[kind]}; using procedural piece fallback.`);
      return null;
    }));
    return cache.get(kind)!;
  };
}
export const loadPieceAsset = createPieceAssetCache();

/** Canvas-owned clones only. Never recolor or dispose cached GLTFLoader originals. */
export function createPieceMaterials() {
  const materials = new Map<string, Material>();
  return {
    material(source: Material, color: string, ghost: boolean): Material {
      const owned = source.name === "PlayerColor";
      if (!owned && !ghost) return source;
      const key = `${source.uuid}:${owned ? color : "neutral"}:${ghost}`;
      if (!materials.has(key)) {
        const copy = source.clone();
        if (owned && copy instanceof MeshStandardMaterial) copy.color.set(color);
        if (ghost) {
          copy.transparent = true; copy.opacity = .46;
          copy.depthWrite = false; copy.depthTest = false;
        }
        materials.set(key, copy);
      }
      return materials.get(key)!;
    },
    dispose() { materials.forEach(material => material.dispose()); materials.clear(); },
  };
}

export function clonePieceScene(template: Object3D, materials: ReturnType<typeof createPieceMaterials>, color: string, ghost: boolean) {
  const scene = template.clone(true);
  scene.traverse(node => {
    node.raycast = ignorePieceRaycast;
    if (node instanceof Mesh) {
      node.material = Array.isArray(node.material)
        ? node.material.map(material => materials.material(material, color, ghost))
        : materials.material(node.material, color, ghost);
      node.castShadow = !ghost; node.receiveShadow = !ghost;
    }
  });
  return scene;
}
