import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import type { Group, Mesh } from "three";
import { BOARD_RIM_TOP, TERRAIN_FALLBACK_OFFSET } from "./coordinates";
import { ignoreTerrainRaycast } from "./terrainAssets";
import { useVisualResources } from "./VisualResources";
import { FOG_IDLE_HZ, fogDispersal, fogProgress, fogQuality, type FogQuality } from "./fogPresentation";

const Presentation = createContext<{ quality: FogQuality; reduced: boolean }>({ quality: "still", reduced: false });

/** One capped clock per scene, never one timer/state update per hex. */
export function FogPresentation({ quality, reduced, connected, hidden, children }: {
  quality: FogQuality; reduced: boolean; connected: boolean; hidden: boolean; children: ReactNode;
}) {
  const pool = useVisualResources();
  const invalidate = useThree(s => s.invalidate);
  const lowPrecision = useThree(s => s.gl.capabilities.precision !== "highp");
  const effective = fogQuality(quality, reduced, lowPrecision);
  useEffect(() => {
    if (!hidden || effective !== "mist" || !connected) return;
    const fog = pool.fog();
    let timer: number | undefined;
    let previous = performance.now();
    const schedule = () => {
      window.clearInterval(timer); timer = undefined;
      if (document.hidden) return;
      previous = performance.now();
      timer = window.setInterval(() => {
        const now = performance.now();
        fog.time.value += Math.min(.2, (now - previous) / 1000); previous = now;
        invalidate();
      }, 1000 / FOG_IDLE_HZ);
    };
    schedule(); document.addEventListener("visibilitychange", schedule);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", schedule); };
  }, [pool, invalidate, effective, connected, hidden]);
  const value = useMemo(() => ({ quality: effective, reduced }), [effective, reduced]);
  return <Presentation.Provider value={value}>{children}</Presentation.Provider>;
}

/** No terrain, number, tile ID or recipe enters the fog's geometry/material factory. */
function FogCover({ started }: { started?: number }) {
  const pool = useVisualResources(), fog = pool.fog();
  const { quality, reduced } = useContext(Presentation);
  const group = useRef<Group>(null), clouds = useRef<Group>(null);
  const indicator = useRef<Mesh>(null);
  const invalidate = useThree(s => s.invalidate);
  const materials = useMemo(() => started == null ? null : fog.revealMaterials(), [fog, started]);
  useEffect(() => () => materials?.dispose(), [materials]);
  const update = () => {
    if (started == null || !materials || !group.current) return false;
    const progress = fogProgress(started, performance.now()), active = !reduced && progress < 1;
    const dispersal = fogDispersal(progress);
    group.current.visible = active;
    group.current.userData.revealing = active;
    if (indicator.current) { indicator.current.visible = active; indicator.current.userData.revealing = active; }
    for (const m of [materials.cloud, materials.haze]) {
      m.opacity = active ? dispersal.opacity : 0;
      m.uniforms.uOpacity.value = m.opacity;
    }
    materials.base.forEach(m => { m.opacity = active ? Math.max(0, 1 - progress * 2.4) : 0; });
    materials.mark.opacity = active ? dispersal.opacity : 0;
    if (clouds.current) {
      clouds.current.position.y = dispersal.lift;
      clouds.current.scale.set(dispersal.spread, 1, dispersal.spread);
    }
    return active;
  };
  useEffect(() => { update(); invalidate(); }, [started, reduced, materials, invalidate]);
  useFrame(() => { if (update()) invalidate(); });
  const reveal = started != null;
  return <group ref={group} userData={{ fogVisual: !reveal, fogQuality: quality }}>
    <mesh position={TERRAIN_FALLBACK_OFFSET} geometry={pool.geometry("hex")}
      material={materials?.base ?? [fog.top, fog.side]} receiveShadow={!reveal} castShadow={!reveal}
      renderOrder={reveal ? 6 : 0} raycast={ignoreTerrainRaycast} />
    {quality === "simple" ? [-.16, 0, .16].map((z, i) => <mesh key={z}
      position={[i * .04, BOARD_RIM_TOP + .018, z]} scale={[.52 - i * .06, .018, .025]}
      ref={i === 0 ? indicator : undefined}
      geometry={pool.geometry("box")} material={materials?.mark ?? fog.mark}
      renderOrder={reveal ? 7 : 0} raycast={ignoreTerrainRaycast}
      userData={{ fogReveal: reveal && i === 0, revealing: reveal }} />) : <group ref={clouds}>
      <mesh position={[0, BOARD_RIM_TOP + .025, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 6]}
        geometry={pool.ring(0, .91, 6)} material={materials?.haze ?? fog.haze}
        renderOrder={reveal ? 7 : 0} raycast={ignoreTerrainRaycast} />
      <mesh ref={indicator} geometry={fog.cloud} material={materials?.cloud ?? fog.mist} renderOrder={reveal ? 8 : 0}
        raycast={ignoreTerrainRaycast} userData={{ fogCloud: true, fogReveal: reveal, revealing: reveal }} />
    </group>}
  </group>;
}

export function FogHexVisual() { return <FogCover />; }

/** Authorized terrain and hit targets mount immediately beneath a finite, non-raycasting veil. */
export function FogRevealVisual({ started }: { started: number }) { return <FogCover started={started} />; }
