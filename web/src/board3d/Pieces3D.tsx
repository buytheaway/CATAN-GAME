import type { ThreeElements } from "@react-three/fiber";
import { useMemo } from "react";
import type { Group } from "three";
import { TILE_TOP } from "./coordinates";
import { playerColor, VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";
import type { Point3D, RenderBuilding, RenderEdge } from "./types";
import PieceVisual from "./PieceVisual";
import type { PieceCue } from "./pieceFeedback";

const ignoreRaycast = () => undefined;
type PieceMeshProps = ThreeElements["mesh"] & {
  kind: Parameters<ReturnType<typeof useVisualResources>["geometry"]>[0];
  color: string; ghost?: boolean;
};

function PieceMesh({ kind, color, ghost = false, ...props }: PieceMeshProps) {
  const pool = useVisualResources();
  return <mesh {...props} geometry={pool.geometry(kind)} material={pool.standard(color, ghost)}
    castShadow={!ghost} receiveShadow={!ghost} {...(ghost ? { raycast: ignoreRaycast } : {})} />;
}

export function Road3D({ road, ghost = false, color = playerColor(road.owner), cue }: { road: RenderEdge; ghost?: boolean; color?: string; cue?: PieceCue }) {
  const pool = useVisualResources();
  return <group position={road.position} rotation={[0, road.rotation, 0]}
    userData={{ edge: road.edge, owner: road.owner, piece: "road", preview: ghost }}>
    <group scale={[road.length, 1, 1]}>
      <PieceVisual kind="road" color={color} ghost={ghost} cue={cue?.owner === road.owner && cue.kind === "road" ? cue : undefined}>
        <mesh geometry={pool.geometry("road")} material={pool.standard(color, ghost)}
          castShadow={!ghost} receiveShadow={!ghost} raycast={ignoreRaycast} />
        <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[0, -.005, 0]}
          scale={[.85, .035, .14]} raycast={ignoreRaycast} />
      </PieceVisual>
    </group>
  </group>;
}

function SettlementFallback({ color, ghost }: { color: string; ghost: boolean }) {
  return <>
    <PieceMesh kind="house" color={color} ghost={ghost} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[0, .014, 0]} scale={[.33, .028, .3]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.trunk} ghost={ghost} position={[-.08, .28, 0]}
      rotation={[0, 0, .72]} scale={[.24, .024, .31]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.trunk} ghost={ghost} position={[.08, .28, 0]}
      rotation={[0, 0, -.72]} scale={[.24, .024, .31]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[0, 0.1, 0.15]} scale={[0.06, 0.1, 0.012]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0, 0.13, -0.15]} scale={[0.07, 0.07, 0.012]} raycast={ignoreRaycast} />
  </>;
}

export function Settlement3D({ building, ghost = false, color = playerColor(building.owner), cue, visible = true }: { building: RenderBuilding; ghost?: boolean; color?: string; cue?: PieceCue; visible?: boolean }) {
  return <group position={building.position} visible={visible} userData={{ vertexId: building.vertexId, owner: building.owner, level: 1, preview: ghost }}>
    <PieceVisual kind="settlement" color={color} ghost={ghost} cue={cue?.owner === building.owner && cue.kind === "settlement" ? cue : undefined}>
      <SettlementFallback color={color} ghost={ghost} />
    </PieceVisual>
  </group>;
}

export function City3D({ building, ghost = false, color = playerColor(building.owner), cue }: { building: RenderBuilding; ghost?: boolean; color?: string; cue?: PieceCue }) {
  const upgrade = cue?.owner === building.owner && cue.kind === "upgrade" ? cue : undefined;
  return <group position={building.position} userData={{ vertexId: building.vertexId, owner: building.owner, level: 2, preview: ghost }}>
    <PieceVisual kind="city" color={color} ghost={ghost} cue={upgrade}>
    <PieceMesh kind="house" color={color} ghost={ghost} position={[-0.1, 0, 0.08]} scale={[1.45, 0.92, 1]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={color} ghost={ghost} position={[0.14, 0.22, -0.13]} scale={[0.26, 0.44, 0.25]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={color} ghost={ghost} position={[0.14, 0.45, -0.13]} scale={[0.31, 0.06, 0.3]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[.02, .015, -.03]} scale={[.51, .03, .49]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.tokenSide} ghost={ghost} position={[.14, .4, -.13]} scale={[.27, .02, .26]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0.14, 0.3, 0.001]} scale={[0.12, 0.09, 0.012]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[-0.1, 0.1, 0.23]} scale={[0.075, 0.11, 0.012]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0.14, 0.3, -0.261]} scale={[0.12, 0.09, 0.012]} raycast={ignoreRaycast} />
    </PieceVisual>
    {!ghost && upgrade && <PieceVisual kind="settlement" color={color} ghost cue={upgrade} upgradeEcho>
      <SettlementFallback color={color} ghost />
    </PieceVisual>}
  </group>;
}

export function ShipBody3D({ length, color, ghost = false }: { length: number; color: string; ghost?: boolean }) {
  return <>
    <PieceMesh kind="hull" color={color} ghost={ghost} scale={[length * 0.88, 1, 1]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.dock} ghost={ghost} position={[0, .14, 0]} scale={[.47, .025, .15]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.trunk} ghost={ghost} position={[-0.1, 0.2, 0]} scale={[0.027, 0.35, 0.027]} raycast={ignoreRaycast} />
    <PieceMesh kind="sail" color={VISUAL.ivory} ghost={ghost} position={[0.03, 0.14, 0.02]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={color} ghost={ghost} position={[0.03, 0.16, 0.05]} scale={[0.26, 0.045, 0.014]} raycast={ignoreRaycast} />
  </>;
}

export function Ship3D({ ship, ghost = false, color = playerColor(ship.owner), visualRef }: {
  ship: RenderEdge; ghost?: boolean; color?: string; visualRef?: (node: Group | null) => void;
}) {
  return <group position={ship.position} rotation={[0, ship.rotation, 0]}
    userData={{ edge: ship.edge, owner: ship.owner, piece: "ship", preview: ghost }}>
    <group ref={visualRef} userData={{ shipVisual: true }}><ShipBody3D length={ship.length} color={color} ghost={ghost} /></group>
  </group>;
}

export function RobberBody3D({ ghost = false }: { ghost?: boolean }) {
  return <>
    <PieceMesh kind="cylinder" color={VISUAL.robber} ghost={ghost} position={[0, 0.035, 0]} scale={[0.18, 0.07, 0.18]} raycast={ignoreRaycast} />
    <PieceMesh kind="cone" color={VISUAL.robber} ghost={ghost} position={[0, 0.22, 0]} scale={[0.14, 0.35, 0.14]} raycast={ignoreRaycast} />
    <PieceMesh kind="sphere" color={VISUAL.robber} ghost={ghost} position={[0, 0.42, 0]} scale={[0.115, 0.115, 0.115]} raycast={ignoreRaycast} />
    <PieceMesh kind="cylinder" color={VISUAL.tokenSide} ghost={ghost} position={[0, 0.33, 0]} scale={[0.09, 0.03, 0.09]} raycast={ignoreRaycast} />
    <PieceMesh kind="cylinder" color={VISUAL.ink} ghost={ghost} position={[0, .077, 0]} scale={[.15, .02, .15]} raycast={ignoreRaycast} />
    <PieceMesh kind="cylinder" color="#e3ccb0" ghost={ghost} position={[0, .01, 0]} scale={[.2, .028, .2]} raycast={ignoreRaycast} />
    <PieceMesh kind="cone" color="#223848" ghost={ghost} position={[0, .245, -.02]} scale={[.17, .36, .145]} raycast={ignoreRaycast} />
    <PieceMesh kind="cylinder" color="#121e2c" ghost={ghost} position={[0, .465, 0]} scale={[.165, .034, .165]} raycast={ignoreRaycast} />
    <PieceMesh kind="cone" color="#121e2c" ghost={ghost} position={[0, .5, 0]} scale={[.125, .11, .125]} raycast={ignoreRaycast} />
  </>;
}

export function Robber3D({ position, tileIndex, visualRef }: { position: Point3D; tileIndex: number; visualRef?: (node: Group | null) => void }) {
  const visualData = useMemo(() => ({ threatVisual: "robber", tileIndex, moving: false, arriving: false }), [tileIndex]);
  return <group position={[position[0] + .48, TILE_TOP, position[2] + .1]} userData={{ tileIndex, piece: "robber" }}>
    <group ref={visualRef} userData={visualData}><RobberBody3D /></group>
  </group>;
}

export function PirateBody3D({ ghost = false }: { ghost?: boolean }) {
  return <>
    <PieceMesh kind="hull" color={VISUAL.pirate} ghost={ghost} scale={[0.95, 1.2, 1.3]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.trunk} ghost={ghost} position={[0, .155, 0]} scale={[.47, .025, .18]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.pirate} ghost={ghost} position={[-0.12, 0.26, 0]} scale={[0.035, 0.38, 0.035]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.pirate} ghost={ghost} position={[0.015, 0.36, 0]} scale={[0.3, 0.18, 0.04]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0.015, 0.36, 0.025]} scale={[0.03, 0.11, 0.01]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0.015, 0.36, 0.026]} scale={[0.1, 0.03, 0.01]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0.015, 0.36, -0.025]} scale={[0.03, 0.11, 0.01]} raycast={ignoreRaycast} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0.015, 0.36, -0.026]} scale={[0.1, 0.03, 0.01]} raycast={ignoreRaycast} />
  </>;
}

export function Pirate3D({ position, tileIndex, visualRef }: { position: Point3D; tileIndex: number; visualRef?: (node: Group | null) => void }) {
  const visualData = useMemo(() => ({ threatVisual: "pirate", tileIndex, moving: false, arriving: false }), [tileIndex]);
  return <group position={[position[0] + 0.15, TILE_TOP + 0.03, position[2] + 0.24]} rotation={[0, -0.3, 0]}
    userData={{ tileIndex, piece: "pirate" }}>
    <group ref={visualRef} userData={visualData}><PirateBody3D /></group>
  </group>;
}
