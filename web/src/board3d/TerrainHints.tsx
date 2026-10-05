import type { ThreeElements } from "@react-three/fiber";
import { TILE_TOP } from "./coordinates";
import { terrainVariation, VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";

const ignoreRaycast = () => undefined;

// Decoration must not intercept tile hover or the controller's larger legal hit areas.
function DetailMesh(props: ThreeElements["mesh"]) {
  return <mesh {...props} raycast={ignoreRaycast} />;
}

function Tree({ x, z, height = 0.42 }: { x: number; z: number; height?: number }) {
  const pool = useVisualResources();
  return <group position={[x, TILE_TOP, z]}>
    <DetailMesh position={[0, 0.08, 0]} scale={[0.035, 0.16, 0.035]}
      geometry={pool.geometry("cylinder")} material={pool.standard(VISUAL.trunk)} />
    <DetailMesh position={[0, height / 2 + 0.08, 0]} scale={[0.22, height, 0.22]} castShadow
      geometry={pool.geometry("cone")} material={pool.standard(VISUAL.tree)} />
    <DetailMesh position={[0, height * 0.7 + 0.08, 0]} scale={[0.16, height * 0.65, 0.16]} castShadow
      geometry={pool.geometry("cone")} material={pool.standard(VISUAL.treeLight)} />
  </group>;
}

/** Static local decoration; original centers, indices and board topology stay untouched. */
export default function TerrainHints({ terrain, tileIndex }: { terrain: string; tileIndex: number }) {
  const variation = terrainVariation(tileIndex);
  return <group rotation={[0, terrain === "sea" ? 0 : variation.rotation, 0]}
    position={[terrain === "sea" ? 0 : variation.offset, 0, 0]}
    scale={terrain === "sea" ? [1, 1, 1] : [variation.scale, 1, variation.scale]}>
    <TerrainDetail terrain={terrain} variation={variation} />
  </group>;
}

function TerrainDetail({ terrain, variation }: { terrain: string; variation: ReturnType<typeof terrainVariation> }) {
  const pool = useVisualResources();
  switch (terrain) {
    case "forest":
      return <><Tree x={-0.43} z={-0.33} height={0.42 * variation.height} />
        <Tree x={0.1 + variation.offset} z={-0.56} height={0.32 / variation.height} />
        <Tree x={0.51} z={-0.2} height={0.38 * variation.scale} /></>;
    case "fields":
      return <group position={[-0.16, TILE_TOP, -0.46]} rotation={[0, -0.2, 0]}>
        {[-0.33, 0, 0.33].map(x => <group key={x} position={[x, 0, x * variation.offset]}
          scale={[1, x === 0 ? variation.height : 1 / variation.height, 1]}>
          <DetailMesh position={[0, 0.015, 0]} scale={[0.19, 0.025, 0.32]}
            geometry={pool.geometry("box")} material={pool.standard(VISUAL.nuggetShade)} />
          {[-0.06, 0.04].map(z => <group key={z} position={[0, 0, z]}>
            <DetailMesh position={[0, 0.115, 0]} scale={[0.025, 0.23, 0.025]}
              geometry={pool.geometry("box")} material={pool.standard(VISUAL.trunk)} />
            <DetailMesh position={[0, 0.26, 0]} scale={[0.06, 0.12, 0.065]} castShadow
              geometry={pool.geometry("rock")} material={pool.standard(VISUAL.wheat)} />
          </group>)}
        </group>)}
      </group>;
    case "pasture":
      return <group position={[-0.3, TILE_TOP + 0.15, -0.42]} rotation={[0, 0.3 + variation.rotation, 0]}>
        <DetailMesh scale={[0.27, 0.16, 0.19]} castShadow
          geometry={pool.geometry("wool")} material={pool.standard(VISUAL.fur)} />
        <DetailMesh position={[0.26, -0.015, 0]} scale={[0.085, 0.1, 0.08]} castShadow
          geometry={pool.geometry("rock")} material={pool.standard(VISUAL.sheep)} />
        {[-0.12, 0.12].flatMap(x => [-0.1, 0.1].map(z => <DetailMesh key={x + ":" + z} position={[x, -0.11, z]}
          scale={[0.045, 0.11, 0.045]} geometry={pool.geometry("box")} material={pool.standard(VISUAL.sheep)} />))}
      </group>;
    case "hills":
    case "desert":
      return <group position={[-0.3, TILE_TOP, -0.42]} rotation={[0, variation.rotation, 0]}>
        <DetailMesh scale={[0.38, (terrain === "hills" ? 0.27 : 0.08) * variation.height, 0.27]} castShadow receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(terrain === "hills" ? VISUAL.clay : VISUAL.sand)} />
        <DetailMesh position={[0.52, 0, 0.08]} scale={[0.25, (terrain === "hills" ? 0.14 : 0.05) / variation.height, 0.19]} receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(terrain === "hills" ? VISUAL.clayLight : VISUAL.sandShade)} />
        {terrain === "desert" && [-0.14, 0.13].map(x => <DetailMesh key={x} position={[x, 0.025, -0.16]}
          rotation={[0, x * 3, 0]} scale={[0.055, 0.035, 0.045]}
          geometry={pool.geometry("rock")} material={pool.standard(VISUAL.sandShade)} />)}
      </group>;
    case "mountains":
      return <group position={[-0.32, TILE_TOP, -0.4]}>
        {[{ x: -0.1, z: 0, h: 0.54 * variation.height, r: 0.28 }, { x: 0.3, z: -0.08, h: 0.38 / variation.height, r: 0.24 }].map(p => <group key={p.x} position={[p.x, 0, p.z]}
          rotation={[0, p.x * 2 + variation.rotation, 0]}>
          <DetailMesh position={[0, p.h / 2, 0]} scale={[p.r, p.h, p.r]} castShadow
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.peak)} />
          <DetailMesh position={[0, p.h * 0.84, 0]} scale={[p.r * 0.33, p.h * 0.33, p.r * 0.33]}
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.snow)} />
        </group>)}
      </group>;
    case "gold":
      return <group position={[-0.28, TILE_TOP, -0.42]}>
        <DetailMesh position={[0, 0.1, 0]} scale={[0.36, 0.18, 0.23]} castShadow
          geometry={pool.geometry("rock")} material={pool.standard(VISUAL.peak)} />
        {[0, 1, 2].map(i => <DetailMesh key={i} position={[-0.17 + i * 0.22, i === 1 ? 0.25 : 0.16, i % 2 * 0.12]}
          rotation={[0, i * 0.7 + variation.rotation, i === 1 ? 0.15 : 0]}
          scale={[0.13, (i === 1 ? 0.18 : 0.13) * variation.height, 0.13]} castShadow
          geometry={pool.geometry("nugget")} material={pool.standard(VISUAL.nugget)} />)}
      </group>;
    case "sea":
      return <group position={[-0.24, TILE_TOP + 0.014, -0.2]}>
        {[0, 1, 2].map(i => <DetailMesh key={i} position={[i * 0.17, 0, i * 0.25]} rotation={[0, -0.35, 0]}
          geometry={pool.geometry("wave")} material={pool.flat(VISUAL.wave, 0.55)} />)}
      </group>;
    default:
      return null;
  }
}
