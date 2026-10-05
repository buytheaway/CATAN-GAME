import type { ThreeElements } from "@react-three/fiber";
import { TILE_TOP } from "./coordinates";
import { playerColor, VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";
import type { Point3D, RenderBuilding, RenderEdge } from "./types";

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

export function Road3D({ road, ghost = false }: { road: RenderEdge; ghost?: boolean }) {
  const pool = useVisualResources();
  return <group position={road.position} rotation={[0, road.rotation, 0]}
    userData={{ edge: road.edge, owner: road.owner, piece: "road", preview: ghost }}>
    <mesh scale={[road.length, 1, 1]} geometry={pool.geometry("road")} material={pool.standard(playerColor(road.owner), ghost)}
      castShadow={!ghost} receiveShadow={!ghost} {...(ghost ? { raycast: ignoreRaycast } : {})} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[0, -.005, 0]}
      scale={[road.length * .85, .035, .14]} />
  </group>;
}

export function Settlement3D({ building, ghost = false }: { building: RenderBuilding; ghost?: boolean }) {
  return <group position={building.position} userData={{ vertexId: building.vertexId, owner: building.owner, level: 1, preview: ghost }}>
    <PieceMesh kind="house" color={playerColor(building.owner)} ghost={ghost} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[0, .014, 0]} scale={[.33, .028, .3]} />
    <PieceMesh kind="box" color={VISUAL.trunk} ghost={ghost} position={[-.08, .28, 0]}
      rotation={[0, 0, .72]} scale={[.24, .024, .31]} />
    <PieceMesh kind="box" color={VISUAL.trunk} ghost={ghost} position={[.08, .28, 0]}
      rotation={[0, 0, -.72]} scale={[.24, .024, .31]} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[0, 0.1, 0.15]} scale={[0.06, 0.1, 0.012]} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0, 0.13, -0.15]} scale={[0.07, 0.07, 0.012]} />
  </group>;
}

export function City3D({ building, ghost = false }: { building: RenderBuilding; ghost?: boolean }) {
  const color = playerColor(building.owner);
  return <group position={building.position} userData={{ vertexId: building.vertexId, owner: building.owner, level: 2, preview: ghost }}>
    <PieceMesh kind="house" color={color} ghost={ghost} position={[-0.1, 0, 0.08]} scale={[1.45, 0.92, 1]} />
    <PieceMesh kind="box" color={color} ghost={ghost} position={[0.14, 0.22, -0.13]} scale={[0.26, 0.44, 0.25]} />
    <PieceMesh kind="box" color={color} ghost={ghost} position={[0.14, 0.45, -0.13]} scale={[0.31, 0.06, 0.3]} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[.02, .015, -.03]} scale={[.51, .03, .49]} />
    <PieceMesh kind="box" color={VISUAL.tokenSide} ghost={ghost} position={[.14, .4, -.13]} scale={[.27, .02, .26]} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0.14, 0.3, 0.001]} scale={[0.12, 0.09, 0.012]} />
    <PieceMesh kind="box" color={VISUAL.ink} ghost={ghost} position={[-0.1, 0.1, 0.23]} scale={[0.075, 0.11, 0.012]} />
    <PieceMesh kind="box" color={VISUAL.ivory} ghost={ghost} position={[0.14, 0.3, -0.261]} scale={[0.12, 0.09, 0.012]} />
  </group>;
}

export function Ship3D({ ship, ghost = false }: { ship: RenderEdge; ghost?: boolean }) {
  return <group position={ship.position} rotation={[0, ship.rotation, 0]}
    userData={{ edge: ship.edge, owner: ship.owner, piece: "ship", preview: ghost }}>
    <PieceMesh kind="hull" color={playerColor(ship.owner)} ghost={ghost} scale={[ship.length * 0.88, 1, 1]} />
    <PieceMesh kind="box" color={VISUAL.dock} ghost={ghost} position={[0, .14, 0]} scale={[.47, .025, .15]} />
    <PieceMesh kind="box" color={VISUAL.trunk} ghost={ghost} position={[-0.1, 0.2, 0]} scale={[0.027, 0.35, 0.027]} />
    <PieceMesh kind="sail" color={VISUAL.ivory} ghost={ghost} position={[0.03, 0.14, 0.02]} />
    <PieceMesh kind="box" color={playerColor(ship.owner)} ghost={ghost} position={[0.03, 0.16, 0.05]} scale={[0.26, 0.045, 0.014]} />
  </group>;
}

export function Robber3D({ position, tileIndex }: { position: Point3D; tileIndex: number }) {
  return <group position={[position[0] + 0.48, TILE_TOP, position[2] + 0.1]} userData={{ tileIndex, piece: "robber" }}>
    <PieceMesh kind="cylinder" color={VISUAL.robber} position={[0, 0.035, 0]} scale={[0.18, 0.07, 0.18]} />
    <PieceMesh kind="cone" color={VISUAL.robber} position={[0, 0.22, 0]} scale={[0.14, 0.35, 0.14]} />
    <PieceMesh kind="sphere" color={VISUAL.robber} position={[0, 0.42, 0]} scale={[0.115, 0.115, 0.115]} />
    <PieceMesh kind="cylinder" color={VISUAL.tokenSide} position={[0, 0.33, 0]} scale={[0.09, 0.03, 0.09]} />
    <PieceMesh kind="cylinder" color={VISUAL.ink} position={[0, .077, 0]} scale={[.15, .02, .15]} />
  </group>;
}

export function Pirate3D({ position, tileIndex }: { position: Point3D; tileIndex: number }) {
  return <group position={[position[0] + 0.15, TILE_TOP + 0.03, position[2] + 0.24]} rotation={[0, -0.3, 0]}
    userData={{ tileIndex, piece: "pirate" }}>
    <PieceMesh kind="hull" color={VISUAL.pirate} scale={[0.95, 1.2, 1.3]} />
    <PieceMesh kind="box" color={VISUAL.trunk} position={[0, .155, 0]} scale={[.47, .025, .18]} />
    <PieceMesh kind="box" color={VISUAL.pirate} position={[-0.12, 0.26, 0]} scale={[0.035, 0.38, 0.035]} />
    <PieceMesh kind="box" color={VISUAL.pirate} position={[0.015, 0.36, 0]} scale={[0.3, 0.18, 0.04]} />
    <PieceMesh kind="box" color={VISUAL.ivory} position={[0.015, 0.36, 0.025]} scale={[0.03, 0.11, 0.01]} />
    <PieceMesh kind="box" color={VISUAL.ivory} position={[0.015, 0.36, 0.026]} scale={[0.1, 0.03, 0.01]} />
    <PieceMesh kind="box" color={VISUAL.ivory} position={[0.015, 0.36, -0.025]} scale={[0.03, 0.11, 0.01]} />
    <PieceMesh kind="box" color={VISUAL.ivory} position={[0.015, 0.36, -0.026]} scale={[0.1, 0.03, 0.01]} />
  </group>;
}
