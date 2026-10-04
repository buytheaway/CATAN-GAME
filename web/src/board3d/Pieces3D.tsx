import { TILE_TOP } from "./coordinates";
import { playerColor } from "./materials";
import type { Point3D, RenderBuilding, RenderEdge } from "./types";

export function Road3D({ road }: { road: RenderEdge }) {
  return (
    <mesh position={road.position} rotation={[0, road.rotation, 0]} castShadow userData={{ edge: road.edge, owner: road.owner }}>
      <boxGeometry args={[road.length * 0.86, 0.12, 0.14]} />
      <meshStandardMaterial color={playerColor(road.owner)} roughness={0.7} />
    </mesh>
  );
}

function House({ color, x = 0, height = 0.22 }: { color: string; x?: number; height?: number }) {
  return (
    <group position={[x, 0, 0]}>
      <mesh position={[0, height / 2, 0]} castShadow>
        <boxGeometry args={[0.26, height, 0.23]} />
        <meshStandardMaterial color={color} roughness={0.75} />
      </mesh>
      <mesh position={[0, height + 0.075, 0]} rotation={[0, Math.PI / 4, 0]} scale={[1, 1, 0.85]} castShadow>
        <coneGeometry args={[0.22, 0.15, 4]} />
        <meshStandardMaterial color={color} roughness={0.75} />
      </mesh>
    </group>
  );
}

export function Settlement3D({ building }: { building: RenderBuilding }) {
  return (
    <group position={building.position} userData={{ vertexId: building.vertexId, owner: building.owner, level: 1 }}>
      <House color={playerColor(building.owner)} />
    </group>
  );
}

export function City3D({ building }: { building: RenderBuilding }) {
  return (
    <group position={building.position} userData={{ vertexId: building.vertexId, owner: building.owner, level: 2 }}>
      <House color={playerColor(building.owner)} x={-0.12} height={0.3} />
      <House color={playerColor(building.owner)} x={0.14} height={0.42} />
    </group>
  );
}

export function Ship3D({ ship }: { ship: RenderEdge }) {
  return (
    <group position={ship.position} rotation={[0, ship.rotation, 0]} userData={{ edge: ship.edge, owner: ship.owner }}>
      <mesh castShadow>
        <boxGeometry args={[ship.length * 0.65, 0.12, 0.2]} />
        <meshStandardMaterial color={playerColor(ship.owner)} />
      </mesh>
      <mesh position={[0, 0.2, 0]} castShadow>
        <boxGeometry args={[0.18, 0.3, 0.035]} />
        <meshStandardMaterial color="#fffdf1" />
      </mesh>
    </group>
  );
}

export function Robber3D({ position, tileIndex }: { position: Point3D; tileIndex: number }) {
  return (
    <group position={[position[0] + 0.46, TILE_TOP, position[2] + 0.15]} userData={{ tileIndex, piece: "robber" }}>
      <mesh position={[0, 0.2, 0]} castShadow>
        <coneGeometry args={[0.14, 0.4, 10]} />
        <meshStandardMaterial color="#394651" />
      </mesh>
      <mesh position={[0, 0.44, 0]} castShadow>
        <sphereGeometry args={[0.1, 10, 8]} />
        <meshStandardMaterial color="#394651" />
      </mesh>
    </group>
  );
}

export function Pirate3D({ position, tileIndex }: { position: Point3D; tileIndex: number }) {
  return (
    <group position={[position[0] + 0.36, TILE_TOP + 0.11, position[2]]} userData={{ tileIndex, piece: "pirate" }}>
      <mesh castShadow><boxGeometry args={[0.42, 0.16, 0.2]} /><meshStandardMaterial color="#394651" /></mesh>
      <mesh position={[0, 0.23, 0]} castShadow><boxGeometry args={[0.04, 0.38, 0.04]} /><meshStandardMaterial color="#394651" /></mesh>
      <mesh position={[0.1, 0.31, 0]}><boxGeometry args={[0.2, 0.16, 0.03]} /><meshStandardMaterial color="#e7edf0" /></mesh>
    </group>
  );
}
