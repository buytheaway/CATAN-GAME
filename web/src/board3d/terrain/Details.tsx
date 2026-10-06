import type { ThreeElements } from "@react-three/fiber";
import { TILE_TOP } from "../coordinates";
import { VISUAL } from "../materials";
import { useVisualResources } from "../VisualResources";

const ignoreRaycast = () => undefined;

// Decoration must not intercept tile hover or the controller's larger legal hit areas.
export function DetailMesh(props: ThreeElements["mesh"]) {
  return <mesh {...props} raycast={ignoreRaycast} />;
}

export function Tree({ x, z, height = 0.42 }: { x: number; z: number; height?: number }) {
  const pool = useVisualResources();
  return <group position={[x, TILE_TOP, z]}>
    <DetailMesh position={[0, 0.08, 0]} scale={[0.035, 0.16, 0.035]}
      geometry={pool.geometry("cylinder")} material={pool.standard(VISUAL.trunk)} />
    <DetailMesh position={[0, height / 2 + 0.08, 0]} scale={[0.22, height, 0.22]} castShadow
      geometry={pool.geometry("cone")} material={pool.standard(VISUAL.tree)} />
    <DetailMesh position={[0, height * 0.7 + 0.08, 0]} scale={[0.16, height * 0.65, 0.16]} castShadow
      geometry={pool.geometry("cone")} material={pool.standard(VISUAL.treeLight)} />
    <DetailMesh position={[0, height * .85 + .08, 0]} scale={[.11, height * .42, .11]}
      geometry={pool.geometry("cone")} material={pool.standard(VISUAL.tree)} />
  </group>;
}

export function Sheep({ x, z, scale = 1, rotation = 0 }: { x: number; z: number; scale?: number; rotation?: number }) {
  const pool = useVisualResources();
  return <group position={[x, TILE_TOP + .14 * scale, z]} rotation={[0, rotation, 0]} scale={scale}>
    <DetailMesh scale={[.2, .13, .15]} castShadow geometry={pool.geometry("wool")} material={pool.standard(VISUAL.fur)} />
    <DetailMesh position={[.19, -.015, 0]} scale={[.07, .085, .07]} castShadow
      geometry={pool.geometry("rock")} material={pool.standard(VISUAL.sheep)} />
    {[-.09, .09].flatMap(x => [-.07, .07].map(z => <DetailMesh key={`${x}:${z}`} position={[x, -.09, z]}
      scale={[.028, .09, .028]} geometry={pool.geometry("box")} material={pool.standard(VISUAL.sheep)} />))}
  </group>;
}
