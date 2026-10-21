import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { useThree } from "@react-three/fiber";
import { BufferGeometry, Color, Float32BufferAttribute, InstancedMesh, Object3D } from "three";
import { DECORATIVE_WATER_TOP } from "./coordinates";
import { ignoreSceneryRaycast } from "./environment";
import { useVisualResources } from "./VisualResources";
import type { buildOceanFrameStrip, OceanLayout } from "./oceanGeometry";
import type { Point3D } from "./types";

type Frame = ReturnType<typeof buildOceanFrameStrip>;
const WATER = ["#286b8b", "#2a6e8c", "#296c87"];

/** Static visual geometry only: no IDs, handlers, rules, timers or frame loop. */
export default function OceanBoard3D({ layout, playable, frame }: {
  layout: OceanLayout; playable: Point3D[]; frame: Frame | null;
}) {
  const pool = useVisualResources();
  const invalidate = useThree(s => s.invalidate);
  const bodies = useRef<InstancedMesh>(null);
  const fills = useRef<InstancedMesh>(null);
  const seams = useRef<InstancedMesh>(null);
  const waves = useRef<InstancedMesh>(null);
  const waterMaterials = useMemo(() => [pool.standard("#75909c"), pool.standard("#ffffff")], [pool]);
  const frameResource = useMemo(() => {
    const geometry = new BufferGeometry();
    if (frame) {
      geometry.setAttribute("position", new Float32BufferAttribute(frame.positions, 3));
      geometry.setIndex(frame.indices);
      geometry.computeVertexNormals();
      geometry.computeBoundingSphere();
    }
    return { geometry, leases: 0 };
  }, [frame]);
  useEffect(() => {
    frameResource.leases++;
    return () => {
      frameResource.leases--;
      // StrictMode's immediate effect remount keeps the live resource leased.
      queueMicrotask(() => { if (!frameResource.leases) frameResource.geometry.dispose(); });
    };
  }, [frameResource]);

  useLayoutEffect(() => {
    const transform = new Object3D(), color = new Color();
    const all = [...playable, ...layout.cells.map(c => c.position)];
    all.forEach((position, index) => {
      transform.position.set(...position);
      transform.rotation.set(0, 0, 0); transform.scale.set(1, 1, 1);
      transform.updateMatrix(); fills.current?.setMatrixAt(index, transform.matrix);
    });
    layout.cells.forEach((cell, index) => {
      transform.position.set(...cell.position);
      transform.rotation.set(0, 0, 0); transform.scale.set(1, 1, 1);
      transform.updateMatrix(); bodies.current?.setMatrixAt(index, transform.matrix);
      bodies.current?.setColorAt(index, color.set(WATER[((cell.q * 31 + cell.r * 17) % 3 + 3) % 3]));
      transform.position.y = DECORATIVE_WATER_TOP + .001;
      transform.rotation.set(-Math.PI / 2, 0, Math.PI / 6);
      transform.updateMatrix(); seams.current?.setMatrixAt(index, transform.matrix);
      for (let wave = 0; wave < 2; wave++) {
        transform.position.set(cell.position[0] - .17 + wave * .32, DECORATIVE_WATER_TOP + .014, cell.position[2] - .1 + wave * .25);
        transform.rotation.set(0, -.35, 0); transform.scale.set(.6, .65, .6);
        transform.updateMatrix(); waves.current?.setMatrixAt(index * 2 + wave, transform.matrix);
      }
    });
    for (const ref of [bodies, fills, seams, waves]) if (ref.current) {
      ref.current.instanceMatrix.needsUpdate = true;
      if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true;
      ref.current.computeBoundingSphere();
    }
    invalidate();
  }, [layout.cells, playable, invalidate]);

  return <group userData={{ decorativeOceanHexes: true, cellCount: layout.cells.length }}>
    {/* A tiled underlay closes existing inset terrain gutters; no rectangular sea substitute. */}
    <instancedMesh ref={fills} args={[pool.geometry("oceanFill"), pool.standard("#20526a"), playable.length + layout.cells.length]}
      raycast={ignoreSceneryRaycast} receiveShadow userData={{ decorativeOceanUnderlay: true }} />
    <instancedMesh ref={bodies} args={[pool.geometry("oceanHex"), waterMaterials, layout.cells.length]}
      raycast={ignoreSceneryRaycast} receiveShadow userData={{ decorativeWaterCells: layout.cells.length }} />
    <instancedMesh ref={seams} args={[pool.ring(.991, 1, 6), pool.flat("#25546a"), layout.cells.length]}
      raycast={ignoreSceneryRaycast} />
    <instancedMesh ref={waves} args={[pool.geometry("wave"), pool.flat("#79a6b8"), layout.cells.length * 2]}
      raycast={ignoreSceneryRaycast} />
    {frame && <mesh geometry={frameResource.geometry} material={pool.standard("#476277")}
      raycast={ignoreSceneryRaycast} receiveShadow userData={{ decorativeOceanFrame: true }} />}
  </group>;
}
