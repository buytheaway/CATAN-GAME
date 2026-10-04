import { TILE_TOP } from "./coordinates";

function Tree({ x, z, height = 0.42 }: { x: number; z: number; height?: number }) {
  return (
    <group position={[x, TILE_TOP, z]}>
      <mesh position={[0, 0.1, 0]} castShadow>
        <cylinderGeometry args={[0.035, 0.045, 0.2, 5]} />
        <meshStandardMaterial color="#76604a" />
      </mesh>
      <mesh position={[0, height / 2 + 0.12, 0]} castShadow>
        <coneGeometry args={[0.18, height, 6]} />
        <meshStandardMaterial color="#245d3b" roughness={1} />
      </mesh>
    </group>
  );
}

/** Small, static silhouettes. Local offsets are decoration, never game geometry. */
export default function TerrainHints({ terrain }: { terrain: string }) {
  switch (terrain) {
    case "forest":
      return <><Tree x={-0.44} z={-0.37} /><Tree x={0.37} z={-0.43} height={0.32} /><Tree x={0.5} z={0.35} height={0.36} /></>;
    case "fields":
      return (
        <group position={[-0.48, TILE_TOP, -0.34]} rotation={[0, -0.25, 0]}>
          {[-0.12, 0, 0.12].map(x => (
            <group key={x} position={[x, 0, 0]}>
              <mesh position={[0, 0.13, 0]} castShadow>
                <boxGeometry args={[0.025, 0.26, 0.025]} />
                <meshStandardMaterial color="#a87926" />
              </mesh>
              <mesh position={[0, 0.29, 0]} scale={[0.055, 0.13, 0.07]} castShadow>
                <icosahedronGeometry args={[1, 0]} />
                <meshStandardMaterial color="#ffe4a1" />
              </mesh>
            </group>
          ))}
        </group>
      );
    case "pasture":
      return (
        <group position={[-0.45, TILE_TOP + 0.11, -0.36]} rotation={[0, 0.4, 0]}>
          <mesh scale={[0.23, 0.13, 0.15]} castShadow>
            <icosahedronGeometry args={[1, 1]} />
            <meshStandardMaterial color="#fffdf1" roughness={1} />
          </mesh>
          <mesh position={[0.22, -0.025, 0]} scale={[0.075, 0.09, 0.075]} castShadow>
            <icosahedronGeometry args={[1, 0]} />
            <meshStandardMaterial color="#535550" />
          </mesh>
          <mesh position={[0, -0.08, 0]}>
            <boxGeometry args={[0.23, 0.08, 0.12]} />
            <meshStandardMaterial color="#6e7858" />
          </mesh>
        </group>
      );
    case "hills":
    case "desert":
      return (
        <group position={[-0.42, TILE_TOP, -0.4]}>
          <mesh scale={[0.32, terrain === "hills" ? 0.23 : 0.1, 0.24]} castShadow receiveShadow>
            <sphereGeometry args={[1, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2]} />
            <meshStandardMaterial color={terrain === "hills" ? "#b76346" : "#f1dfb5"} roughness={1} />
          </mesh>
          <mesh position={[0.43, 0, 0]} scale={[0.21, 0.1, 0.17]} castShadow>
            <sphereGeometry args={[1, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2]} />
            <meshStandardMaterial color={terrain === "hills" ? "#e5a07d" : "#d5bc88"} roughness={1} />
          </mesh>
        </group>
      );
    case "mountains":
      return (
        <group position={[-0.42, TILE_TOP, -0.4]}>
          <mesh position={[0, 0.25, 0]} castShadow>
            <coneGeometry args={[0.29, 0.5, 5]} />
            <meshStandardMaterial color="#647b90" flatShading roughness={1} />
          </mesh>
          <mesh position={[0.32, 0.17, 0.05]} castShadow>
            <coneGeometry args={[0.22, 0.34, 5]} />
            <meshStandardMaterial color="#d6e0e7" flatShading roughness={1} />
          </mesh>
        </group>
      );
    case "gold":
      return (
        <group position={[-0.43, TILE_TOP + 0.14, -0.4]}>
          {[0, 1, 2].map(i => (
            <mesh key={i} position={[i * 0.15, i === 1 ? 0.07 : 0, i % 2 * 0.1]} scale={[0.13, 0.18, 0.12]} castShadow>
              <octahedronGeometry args={[1]} />
              <meshStandardMaterial color="#ffe38c" metalness={0.25} roughness={0.55} />
            </mesh>
          ))}
        </group>
      );
    case "sea":
      return (
        <group position={[-0.3, TILE_TOP + 0.01, -0.18]}>
          {[0, 1, 2].map(i => (
            <mesh key={i} position={[i * 0.12, 0, i * 0.23]} rotation={[-Math.PI / 2, 0, 0]}>
              <planeGeometry args={[0.55, 0.025]} />
              <meshBasicMaterial color="#c4e6ed" />
            </mesh>
          ))}
        </group>
      );
    default:
      return null;
  }
}
