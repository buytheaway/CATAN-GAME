import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Group, Mesh, Material } from "three";
import { DIE_PIPS, DICE_DURATION_MS, DICE_SETTLED_MS, DICE_FADE_MS, diceOpacity, diePose, type DiceRollVisual } from "../game/dice";
import { useVisualResources } from "./VisualResources";
import type { Point3D } from "./types";

const ignoreRaycast = () => undefined;
const cubeFaces = [
  { face: 1, position: [0, .427, 0], rotation: [-Math.PI / 2, 0, 0] },
  { face: 2, position: [0, 0, .427], rotation: [0, 0, 0] },
  { face: 3, position: [.427, 0, 0], rotation: [0, Math.PI / 2, 0] },
  { face: 4, position: [-.427, 0, 0], rotation: [0, -Math.PI / 2, 0] },
  { face: 5, position: [0, 0, -.427], rotation: [0, Math.PI, 0] },
  { face: 6, position: [0, -.427, 0], rotation: [Math.PI / 2, 0, 0] },
];

function Die({ face }: { face: number }) {
  const pool = useVisualResources();
  // Fade belongs to this animation, never to the shared material pool.
  const materials = useMemo(() => {
    const body = pool.standard("#fff7e9").clone(), pips = pool.flat("#172533").clone();
    body.transparent = pips.transparent = true;
    return { body, pips };
  }, [pool]);
  useEffect(() => () => { materials.body.dispose(); materials.pips.dispose(); }, [materials]);
  return <group userData={{ serverFace: face }}>
    <mesh geometry={pool.geometry("die")} material={materials.body} castShadow raycast={ignoreRaycast} />
    {cubeFaces.map(f => <group key={f.face} position={f.position as Point3D} rotation={f.rotation as Point3D}>
      {DIE_PIPS[f.face].map(([x, y]) => <mesh key={`${x}:${y}`} position={[x * .2, y * .2, 0]} scale={.055}
        raycast={ignoreRaycast} geometry={pool.geometry("disc")} material={materials.pips} />)}
    </group>)}
  </group>;
}

/** Mounted only for an accepted roll. Invalidation stops when the finite choreography ends. */
export default function DiceRoll3D({ roll, center }: { roll: DiceRollVisual; center: Point3D }) {
  const group = useRef<Group>(null);
  const invalidate = useThree(s => s.invalidate);
  useEffect(() => {
    const timer = window.setTimeout(invalidate, Math.max(0, DICE_FADE_MS - (performance.now() - roll.startedAt)));
    return () => window.clearTimeout(timer);
  }, [roll.startedAt, invalidate]);
  useFrame(() => {
    if (!group.current) return;
    const elapsed = performance.now() - roll.startedAt;
    const progress = elapsed / DICE_DURATION_MS;
    group.current.children.forEach((die, i) => {
      const pose = diePose(progress, roll.faces[i], i);
      die.position.set(...pose.position); die.rotation.set(...pose.rotation);
    });
    group.current.traverse(object => { if (object instanceof Mesh) {
      const material = object.material as Material;
      material.opacity = diceOpacity(elapsed);
    } });
    if (elapsed < DICE_SETTLED_MS || (elapsed >= DICE_FADE_MS && elapsed < DICE_DURATION_MS)) invalidate();
  });
  return <group ref={group} position={[center[0], 0, center[2]]} userData={{ diceRoll: roll.id }}>
    {roll.faces.map((face, i) => <group key={i}><Die face={face} /></group>)}
  </group>;
}
