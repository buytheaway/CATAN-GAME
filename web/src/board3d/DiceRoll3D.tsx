import { useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Group } from "three";
import { DIE_PIPS, DICE_DURATION_MS, diePose, type DiceRollVisual } from "../game/dice";
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
  return <group userData={{ serverFace: face }}>
    <mesh geometry={pool.geometry("die")} material={pool.standard("#fff7e9")} castShadow raycast={ignoreRaycast} />
    {cubeFaces.map(f => <group key={f.face} position={f.position as Point3D} rotation={f.rotation as Point3D}>
      {DIE_PIPS[f.face].map(([x, y]) => <mesh key={`${x}:${y}`} position={[x * .2, y * .2, 0]} scale={.055}
        raycast={ignoreRaycast} geometry={pool.geometry("disc")} material={pool.flat("#172533")} />)}
    </group>)}
  </group>;
}

/** Mounted only for an accepted roll. Invalidation stops when the finite choreography ends. */
export default function DiceRoll3D({ roll, center }: { roll: DiceRollVisual; center: Point3D }) {
  const group = useRef<Group>(null);
  const invalidate = useThree(s => s.invalidate);
  useFrame(() => {
    if (!group.current) return;
    const progress = (performance.now() - roll.startedAt) / DICE_DURATION_MS;
    group.current.children.forEach((die, i) => {
      const pose = diePose(progress, roll.faces[i], i);
      die.position.set(...pose.position); die.rotation.set(...pose.rotation);
    });
    if (progress < 1) invalidate();
  });
  return <group ref={group} position={[center[0], 0, center[2]]} userData={{ diceRoll: roll.id }}>
    {roll.faces.map((face, i) => <group key={i}><Die face={face} /></group>)}
  </group>;
}
