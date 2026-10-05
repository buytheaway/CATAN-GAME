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
    <DetailMesh position={[0, height * .85 + .08, 0]} scale={[.11, height * .42, .11]}
      geometry={pool.geometry("cone")} material={pool.standard(VISUAL.tree)} />
  </group>;
}

function Sheep({ x, z, scale = 1, rotation = 0 }: { x: number; z: number; scale?: number; rotation?: number }) {
  const pool = useVisualResources();
  return <group position={[x, TILE_TOP + .14 * scale, z]} rotation={[0, rotation, 0]} scale={scale}>
    <DetailMesh scale={[.2, .13, .15]} castShadow geometry={pool.geometry("wool")} material={pool.standard(VISUAL.fur)} />
    <DetailMesh position={[.19, -.015, 0]} scale={[.07, .085, .07]} castShadow
      geometry={pool.geometry("rock")} material={pool.standard(VISUAL.sheep)} />
    {[-.09, .09].flatMap(x => [-.07, .07].map(z => <DetailMesh key={`${x}:${z}`} position={[x, -.09, z]}
      scale={[.028, .09, .028]} geometry={pool.geometry("box")} material={pool.standard(VISUAL.sheep)} />))}
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
      return <>{[[-.55, -.35], [-.32, -.66], [.03, -.67], [.38, -.54], [.58, -.24], [-.68, .02], [.67, .08]]
        .map(([x, z], i) => <Tree key={i} x={x} z={z} height={(.38 + i % 3 * .085) * variation.height} />)}</>;
    case "fields":
      return <group position={[0, TILE_TOP, -.48]} rotation={[0, -.12, 0]}>
        {[-.58, -.29, 0, .29, .58].map(x => <group key={x} position={[x, 0, Math.abs(x) * .33]}
          scale={[1, x === 0 ? variation.height : 1 / variation.height, 1]}>
          <DetailMesh position={[0, .012, 0]} scale={[.16, .023, .35]}
            geometry={pool.geometry("box")} material={pool.standard(VISUAL.nuggetShade)} />
          {[-.12, 0, .12].map(z => <group key={z} position={[0, 0, z]}>
            <DetailMesh position={[0, .13, 0]} scale={[.022, .26, .022]}
              geometry={pool.geometry("box")} material={pool.standard(VISUAL.trunk)} />
            <DetailMesh position={[0, .28, 0]} scale={[.065, .14, .065]} castShadow
              geometry={pool.geometry("rock")} material={pool.standard(VISUAL.wheat)} />
          </group>)}
        </group>)}
      </group>;
    case "pasture":
      return <><Sheep x={-.4} z={-.4} rotation={.3} /><Sheep x={.3} z={-.55} scale={.8} rotation={-.6} />
        <Sheep x={.62} z={-.02} scale={.62} rotation={1.2} />
        {[[-.64, .12], [-.06, -.69], [.55, .45], [-.48, .52]].map(([x, z], i) => <group key={i} position={[x, TILE_TOP, z]}>
          <DetailMesh position={[0, .035, 0]} scale={[.055, .07, .055]}
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.treeLight)} />
          <DetailMesh position={[.06, .025, .03]} scale={[.04, .05, .04]}
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.tree)} />
        </group>)}</>;
    case "hills":
    case "desert":
      return <group position={[-0.3, TILE_TOP, -0.42]} rotation={[0, variation.rotation, 0]}>
        <DetailMesh scale={[0.38, (terrain === "hills" ? 0.27 : 0.08) * variation.height, 0.27]} castShadow receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(terrain === "hills" ? VISUAL.clay : VISUAL.sand)} />
        <DetailMesh position={[0.52, 0, 0.08]} scale={[0.25, (terrain === "hills" ? 0.14 : 0.05) / variation.height, 0.19]} receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(terrain === "hills" ? VISUAL.clayLight : VISUAL.sandShade)} />
        <DetailMesh position={[-.28, 0, .25]} scale={[.17, terrain === "hills" ? .18 : .055, .28]} receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(terrain === "hills" ? VISUAL.clayLight : VISUAL.sand)} />
        {[-.18, .12, .5].map(x => <DetailMesh key={x} position={[x, .025, -.16]} rotation={[0, x * 3, 0]}
          scale={[.065, .045, .05]} geometry={pool.geometry("rock")}
          material={pool.standard(terrain === "hills" ? VISUAL.clay : VISUAL.sandShade)} />)}
      </group>;
    case "mountains":
      return <group position={[-0.32, TILE_TOP, -0.4]}>
        {[{ x: -.12, z: -.06, h: .69 * variation.height, r: .31 }, { x: .34, z: -.15, h: .52 / variation.height, r: .26 },
          { x: .7, z: .08, h: .31, r: .18 }].map(p => <group key={p.x} position={[p.x, 0, p.z]}
          rotation={[0, p.x * 2 + variation.rotation, 0]}>
          <DetailMesh position={[0, p.h / 2, 0]} scale={[p.r, p.h, p.r]} castShadow
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.peak)} />
          <DetailMesh position={[0, p.h * 0.84, 0]} scale={[p.r * 0.33, p.h * 0.33, p.r * 0.33]}
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.snow)} />
        </group>)}
      </group>;
    case "gold":
      return <group position={[-0.28, TILE_TOP, -0.42]}>
        <DetailMesh position={[0, .14, 0]} scale={[.39, .27, .24]} castShadow
          geometry={pool.geometry("rock")} material={pool.standard(VISUAL.peak)} />
        <DetailMesh position={[.46, .1, .07]} scale={[.24, .18, .2]} castShadow
          geometry={pool.geometry("rock")} material={pool.standard(VISUAL.peak)} />
        {[0, 1, 2, 3, 4].map(i => <DetailMesh key={i} position={[-.24 + i * .18, i === 1 ? .35 : .16, i % 2 * .15]}
          rotation={[0, i * 0.7 + variation.rotation, i === 1 ? 0.15 : 0]}
          scale={[0.13, (i === 1 ? 0.18 : 0.13) * variation.height, 0.13]} castShadow
          geometry={pool.geometry("nugget")} material={pool.standard(VISUAL.nugget)} />)}
      </group>;
    case "sea":
      return <group position={[-0.24, TILE_TOP + 0.014, -0.2]}>
        {[0, 1, 2, 3, 4].map(i => <DetailMesh key={i} position={[-.22 + i % 3 * .25, 0, -.15 + Math.floor(i / 3) * .35]}
          rotation={[0, -.35 + i % 2 * .15, 0]}
          geometry={pool.geometry("wave")} material={pool.flat(VISUAL.wave, 0.55)} />)}
      </group>;
    default:
      return null;
  }
}
