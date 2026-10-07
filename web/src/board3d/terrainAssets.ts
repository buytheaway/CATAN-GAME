import { Mesh, type Object3D } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

export const TERRAIN_ASSET_URLS = {
  forest: "/models/terrain/forest.glb",
  fields: "/models/terrain/fields.glb",
  pasture: "/models/terrain/pasture.glb",
  hills: "/models/terrain/hills.glb",
  mountains: "/models/terrain/mountains.glb",
  desert: "/models/terrain/desert.glb",
  sea: "/models/terrain/sea.glb",
  gold: "/models/terrain/gold.glb",
} as const;

export type TerrainAssetName = keyof typeof TERRAIN_ASSET_URLS;
const aliases: Record<string, TerrainAssetName> = {
  wood: "forest", wheat: "fields", sheep: "pasture", clay: "hills", brick: "hills", ore: "mountains",
};

export function terrainAssetName(terrain: string): TerrainAssetName | null {
  if (Object.prototype.hasOwnProperty.call(TERRAIN_ASSET_URLS, terrain)) return terrain as TerrainAssetName;
  return Object.prototype.hasOwnProperty.call(aliases, terrain) ? aliases[terrain] : null;
}

/** All eight assets share a radius-1.2 flat-top base and a bottom at source Y=-0.11. */
export const TERRAIN_TRANSFORM = {
  scale: 1 / 1.2,
  rotationY: Math.PI / 2,
  sourceLift: 0.11,
  lift: 0.11 / 1.2,
} as const;

export const ignoreTerrainRaycast = () => undefined;

/** Own scene nodes per hex; the cached source, geometry and materials remain unchanged. */
export function cloneTerrainScene(template: Object3D): Object3D {
  const scene = template.clone(true);
  scene.traverse(node => {
    node.raycast = ignoreTerrainRaycast;
    if (node instanceof Mesh) { node.castShadow = true; node.receiveShadow = true; }
  });
  return scene;
}

/** Bounded to eight assets, including failed loads. No per-hex fetches or repeated warnings. */
export function createTerrainAssetCache(
  load: (url: string) => Promise<Object3D> = url => new GLTFLoader().loadAsync(url).then(gltf => gltf.scene),
  warn: (message: string) => void = message => console.warn(message),
) {
  const cache = new Map<TerrainAssetName, Promise<Object3D | null>>();
  return (terrain: string): Promise<Object3D | null> => {
    const name = terrainAssetName(terrain);
    if (!name) return Promise.resolve(null);
    if (!cache.has(name)) {
      const url = TERRAIN_ASSET_URLS[name];
      cache.set(name, Promise.resolve().then(() => load(url)).catch(() => {
        warn(`[Board3D] Could not load ${url}; using procedural terrain fallback.`);
        return null;
      }));
    }
    return cache.get(name)!;
  };
}

export const loadTerrainAsset = createTerrainAssetCache();
