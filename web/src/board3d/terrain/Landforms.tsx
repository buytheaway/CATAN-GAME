import { TILE_TOP } from "../coordinates";
import { terrainVariation, VISUAL } from "../materials";
import { useVisualResources } from "../VisualResources";
import { DetailMesh } from "./Details";
type Props = { variation: ReturnType<typeof terrainVariation> };

export function HillsVisual({ variation }: Props) {
  const pool = useVisualResources();
  return <group position={[-0.3, TILE_TOP, -0.42]} rotation={[0, variation.rotation, 0]}>
        <DetailMesh scale={[0.38, (0.27) * variation.height, 0.27]} castShadow receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(VISUAL.clay)} />
        <DetailMesh position={[0.52, 0, 0.08]} scale={[0.25, (0.14) / variation.height, 0.19]} receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(VISUAL.clayLight)} />
        <DetailMesh position={[-.28, 0, .25]} scale={[.17, .18, .28]} receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(VISUAL.clayLight)} />
        {[-.18, .12, .5].map(x => <DetailMesh key={x} position={[x, .025, -.16]} rotation={[0, x * 3, 0]}
          scale={[.065, .045, .05]} geometry={pool.geometry("rock")}
          material={pool.standard(VISUAL.clay)} />)}
        <DetailMesh position={[.25, .04, .29]} rotation={[0, .3, .12]} scale={[.26, .1, .12]} geometry={pool.geometry("rock")} material={pool.standard(VISUAL.clay)} />
      </group>;
}

export function MountainsVisual({ variation }: Props) {
  const pool = useVisualResources();
  return <group position={[-0.32, TILE_TOP, -0.4]}>
        {[{ x: -.12, z: -.06, h: .69 * variation.height, r: .31 }, { x: .34, z: -.15, h: .52 / variation.height, r: .26 },
          { x: .7, z: .08, h: .31, r: .18 }].map(p => <group key={p.x} position={[p.x, 0, p.z]}
          rotation={[0, p.x * 2 + variation.rotation, 0]}>
          <DetailMesh position={[0, p.h / 2, 0]} scale={[p.r, p.h, p.r]} castShadow
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.peak)} />
          <DetailMesh position={[0, p.h * 0.84, 0]} scale={[p.r * 0.33, p.h * 0.33, p.r * 0.33]}
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.snow)} />
        </group>)}
        <DetailMesh position={[.2, .055, .22]} scale={[.24, .11, .16]} geometry={pool.geometry("rock")} material={pool.standard(VISUAL.peak)} />
        <DetailMesh position={[.42, .05, .23]} scale={[.075, .065, .08]} geometry={pool.geometry("nugget")} material={pool.standard("#8da3aa")} />
      </group>;
}

export function DesertVisual({ variation }: Props) {
  const pool = useVisualResources();
  return <group position={[-0.3, TILE_TOP, -0.42]} rotation={[0, variation.rotation, 0]}>
        <DetailMesh scale={[0.38, (0.08) * variation.height, 0.27]} castShadow receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(VISUAL.sand)} />
        <DetailMesh position={[0.52, 0, 0.08]} scale={[0.25, (0.05) / variation.height, 0.19]} receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(VISUAL.sandShade)} />
        <DetailMesh position={[-.28, 0, .25]} scale={[.17, .055, .28]} receiveShadow
          geometry={pool.geometry("dome")} material={pool.standard(VISUAL.sand)} />
        {[-.18, .12, .5].map(x => <DetailMesh key={x} position={[x, .025, -.16]} rotation={[0, x * 3, 0]}
          scale={[.065, .045, .05]} geometry={pool.geometry("rock")}
          material={pool.standard(VISUAL.sandShade)} />)}
        <DetailMesh position={[.62, .095, .12]} scale={[.027, .19, .027]} geometry={pool.geometry("box")} material={pool.standard(VISUAL.trunk)} />
        <DetailMesh position={[.65, .15, .12]} rotation={[0, 0, .8]} scale={[.07, .018, .018]} geometry={pool.geometry("box")} material={pool.standard(VISUAL.trunk)} />
      </group>;
}

export function GoldVisual({ variation }: Props) {
  const pool = useVisualResources();
  return <group position={[-0.28, TILE_TOP, -0.42]}>
        <DetailMesh position={[0, .14, 0]} scale={[.39, .27, .24]} castShadow
          geometry={pool.geometry("rock")} material={pool.standard(VISUAL.peak)} />
        <DetailMesh position={[.46, .1, .07]} scale={[.24, .18, .2]} castShadow
          geometry={pool.geometry("rock")} material={pool.standard(VISUAL.peak)} />
        <DetailMesh position={[.23, .15, -.11]} rotation={[0, .3, .12]} scale={[.39, .022, .025]} geometry={pool.geometry("box")} material={pool.standard(VISUAL.nugget)} />
        {[0, 1, 2, 3, 4].map(i => <DetailMesh key={i} position={[-.24 + i * .18, i === 1 ? .35 : .16, i % 2 * .15]}
          rotation={[0, i * 0.7 + variation.rotation, i === 1 ? 0.15 : 0]}
          scale={[0.13, (i === 1 ? 0.18 : 0.13) * variation.height, 0.13]} castShadow
          geometry={pool.geometry("nugget")} material={pool.standard(VISUAL.nugget)} />)}
      </group>;
}
