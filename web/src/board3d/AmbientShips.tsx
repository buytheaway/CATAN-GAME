import { useEffect, useRef } from "react";
import { useThree } from "@react-three/fiber";
import type { Group } from "three";
import type { Point3D } from "./types";
import { useVisualResources } from "./VisualResources";
import { ambientBoatPose, ignoreSceneryRaycast } from "./environment";
import { VISUAL } from "./materials";

const BOATS = [0, 1, 2];

/** Neutral scenery, deliberately unlike owner-coloured playable ships. */
export default function AmbientShips({ center, clearance }: { center: Point3D; clearance: number }) {
  const pool = useVisualResources();
  const boats = useRef<(Group | null)[]>([]);
  const seconds = useRef(0);
  const invalidate = useThree(s => s.invalidate);
  const [x, , z] = center;
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: number | undefined;
    let previous = performance.now();
    const update = () => {
      const now = performance.now();
      seconds.current += Math.min(.2, (now - previous) / 1000); previous = now;
      boats.current.forEach((mesh, i) => {
        if (!mesh) return;
        const pose = ambientBoatPose([x, 0, z], clearance, i, seconds.current);
        mesh.position.set(...pose.position); mesh.rotation.y = pose.rotation;
      });
      invalidate();
    };
    const schedule = () => {
      window.clearInterval(timer); timer = undefined;
      if (!document.hidden && !reduced.matches) {
        previous = performance.now();
        // Slow sailing needs only ten updates/sec; keep the existing demand renderer.
        timer = window.setInterval(update, 100);
      }
    };
    schedule();
    document.addEventListener("visibilitychange", schedule); reduced.addEventListener("change", schedule);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", schedule); reduced.removeEventListener("change", schedule);
    };
  }, [x, z, clearance, invalidate]);
  return <group userData={{ ambientShips: true }}>{BOATS.map(i => {
    const pose = ambientBoatPose(center, clearance, i, seconds.current);
    return <group key={i} ref={node => { boats.current[i] = node; }} position={pose.position}
      rotation={[0, pose.rotation, 0]} userData={{ decorativeBoat: true }}>
      <group scale={.65}>
        <mesh geometry={pool.geometry("hull")} material={pool.standard("#6c8790")} raycast={ignoreSceneryRaycast} />
        <mesh position={[0, .23, 0]} scale={[.022, .5, .022]} geometry={pool.geometry("box")}
          material={pool.standard(VISUAL.trunk)} raycast={ignoreSceneryRaycast} />
        <mesh position={[0, .12, .015]} scale={[1.2, 1.8, 1.2]} geometry={pool.geometry("sail")}
          material={pool.standard("#dccfba")} raycast={ignoreSceneryRaycast} />
        <mesh position={[-.05, .16, -.025]} rotation={[0, Math.PI, 0]} scale={[.75, .75, .75]}
          geometry={pool.geometry("sail")} material={pool.standard("#b6d0cd")} raycast={ignoreSceneryRaycast} />
      </group>
    </group>;
  })}</group>;
}
