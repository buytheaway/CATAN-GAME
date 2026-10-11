import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import type { Mesh, MeshBasicMaterial } from "three";
import { FOG_REVEAL_MS } from "../board/fogReveal";
import { useReducedMotion } from "../game/motion";
import { BOARD_RIM_TOP, TERRAIN_FALLBACK_OFFSET, TILE_TOP } from "./coordinates";
import { ignoreTerrainRaycast } from "./terrainAssets";
import { useVisualResources } from "./VisualResources";

/** Identical procedural visual for every unknown tile. No asset lookup or hidden input. */
export function FogHexVisual() {
  const pool = useVisualResources();
  return <group userData={{ fogVisual: true }}>
    <mesh position={TERRAIN_FALLBACK_OFFSET} geometry={pool.geometry("hex")}
      material={[pool.standard("#526879"), pool.standard("#354958")]}
      receiveShadow castShadow raycast={ignoreTerrainRaycast} />
    {[-.16, 0, .16].map((z, i) => <mesh key={z} position={[i * .04, BOARD_RIM_TOP + .018, z]}
      scale={[.52 - i * .06, .018, .025]} geometry={pool.geometry("box")}
      material={pool.flat("#a6beca")} raycast={ignoreTerrainRaycast} />)}
  </group>;
}

/** Finite presentation veil. Logical hit geometry and latest terrain never wait for animation. */
export function FogRevealVisual({ started }: { started: number }) {
  const pool = useVisualResources();
  const mesh = useRef<Mesh>(null);
  const material = useRef<MeshBasicMaterial>(null);
  const reduced = useReducedMotion();
  const invalidate = useThree(s => s.invalidate);
  const update = () => {
    const elapsed = performance.now() - started;
    const active = !reduced && elapsed < FOG_REVEAL_MS;
    if (mesh.current) { mesh.current.visible = active; mesh.current.userData.revealing = active; }
    if (material.current) material.current.opacity = active ? .48 * (1 - Math.max(0, elapsed) / FOG_REVEAL_MS) : 0;
    return active;
  };
  useEffect(() => { update(); invalidate(); }, [started, reduced, invalidate]);
  useFrame(() => { if (update()) invalidate(); });
  return <mesh ref={mesh} position={[0, TILE_TOP + .045, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 6]}
    geometry={pool.ring(0, .94, 6)} renderOrder={6} raycast={ignoreTerrainRaycast}
    userData={{ fogReveal: true }}>
    <meshBasicMaterial ref={material} color="#a6beca" transparent depthWrite={false} />
  </mesh>;
}
