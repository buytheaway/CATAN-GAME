import { useEffect, useMemo, useState } from "react";
import type { Object3D } from "three";
import { terrainStyle } from "./materials";
import TerrainHints from "./TerrainHints";
import {
  cloneTerrainScene, ignoreTerrainRaycast, loadTerrainAsset, terrainAssetName, TERRAIN_TRANSFORM,
} from "./terrainAssets";
import { useVisualResources } from "./VisualResources";

/** Presentation only. The parent hex retains the original logical hit geometry and IDs. */
export default function TerrainHexVisual({ terrain, tileIndex }: { terrain: string; tileIndex: number }) {
  const name = terrainAssetName(terrain);
  const [loaded, setLoaded] = useState<{ name: typeof name; template: Object3D | null }>({ name: null, template: null });
  useEffect(() => {
    let active = true;
    if (name) loadTerrainAsset(name).then(template => { if (active) setLoaded({ name, template }); });
    return () => { active = false; };
  }, [name]);
  const template = loaded.name === name ? loaded.template : null;
  const scene = useMemo(() => template ? cloneTerrainScene(template) : null, [template]);
  const pool = useVisualResources();
  const style = terrainStyle(name ?? terrain);

  if (!scene) return <group userData={{ terrainFallback: name ?? terrain }}>
    <mesh geometry={pool.geometry("hex")} material={[pool.standard(style.color), pool.standard(style.side)]}
      receiveShadow castShadow raycast={ignoreTerrainRaycast} />
    <TerrainHints terrain={name ?? terrain} tileIndex={tileIndex} />
  </group>;

  return <group position={[0, TERRAIN_TRANSFORM.lift, 0]} rotation={[0, TERRAIN_TRANSFORM.rotationY, 0]}
    scale={TERRAIN_TRANSFORM.scale} userData={{ terrainAsset: name }}>
    {/* Cached geometry/materials outlive individual hexes and 2D/3D toggles. */}
    <primitive object={scene} dispose={null} />
  </group>;
}
