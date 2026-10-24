import { useEffect, useMemo, useState } from "react";
import type { Object3D } from "three";
import { terrainStyle } from "./materials";
import TerrainHints from "./TerrainHints";
import {
  cloneTerrainScene, ignoreTerrainRaycast, loadTerrainAsset, terrainAssetName, TERRAIN_TRANSFORM,
} from "./terrainAssets";
import { useVisualResources } from "./VisualResources";
import { TERRAIN_FALLBACK_OFFSET } from "./coordinates";
import { clearRobberVegetation } from "./terrainReadability";

/** Presentation only. The parent hex retains the original logical hit geometry and IDs. */
export default function TerrainHexVisual({ terrain, tileIndex, robberClearance = false }: { terrain: string; tileIndex: number; robberClearance?: boolean }) {
  const name = terrainAssetName(terrain);
  const [loaded, setLoaded] = useState<{ name: typeof name; template: Object3D | null }>({ name: null, template: null });
  useEffect(() => {
    let active = true;
    if (name) loadTerrainAsset(name).then(template => { if (active) setLoaded({ name, template }); });
    return () => { active = false; };
  }, [name]);
  const template = loaded.name === name ? loaded.template : null;
  const scene = useMemo(() => {
    if (!template) return null;
    const clone = cloneTerrainScene(template);
    if (robberClearance) clearRobberVegetation(clone);
    return clone;
  }, [template, robberClearance]);
  const pool = useVisualResources();
  const style = terrainStyle(name ?? terrain);

  if (!scene) return <group position={TERRAIN_FALLBACK_OFFSET} userData={{ terrainFallback: name ?? terrain }}>
    <mesh geometry={pool.geometry("hex")} material={[pool.standard(style.color), pool.standard(style.side)]}
      receiveShadow castShadow raycast={ignoreTerrainRaycast} />
    {!robberClearance && <TerrainHints terrain={name ?? terrain} tileIndex={tileIndex} />}
  </group>;

  return <group position={[0, TERRAIN_TRANSFORM.lift, 0]} rotation={[0, TERRAIN_TRANSFORM.rotationY, 0]}
    scale={TERRAIN_TRANSFORM.scale} userData={{ terrainAsset: name }}>
    {/* Cached geometry/materials outlive individual hexes and 2D/3D toggles. */}
    <primitive object={scene} dispose={null} />
  </group>;
}
