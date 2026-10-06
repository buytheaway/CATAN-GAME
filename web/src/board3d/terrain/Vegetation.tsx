import { TILE_TOP } from "../coordinates";
import { terrainVariation, VISUAL } from "../materials";
import { useVisualResources } from "../VisualResources";
import { DetailMesh, Tree, Sheep } from "./Details";
type Props = { variation: ReturnType<typeof terrainVariation> };

export function ForestVisual({ variation }: Props) {
  const pool = useVisualResources();
  return <>{[[-.55, -.35], [-.32, -.66], [.03, -.67], [.38, -.54], [.58, -.24], [-.68, .02], [.67, .08], [-.48, .4], [.4, .45]]
        .map(([x, z], i) => <Tree key={i} x={x} z={z} height={(.34 + i % 3 * .07) * variation.height} />)}
      <DetailMesh position={[-.68, TILE_TOP + .03, .23]} scale={[.095, .065, .07]} geometry={pool.geometry("rock")} material={pool.standard(VISUAL.peak)} />
      <DetailMesh position={[.62, TILE_TOP + .04, .27]} scale={[.055, .08, .055]} geometry={pool.geometry("cylinder")} material={pool.standard(VISUAL.trunk)} />
    </>;
}

export function FieldsVisual({ variation }: Props) {
  const pool = useVisualResources();
  return <group position={[0, TILE_TOP, -.48]} rotation={[0, -.12, 0]}>
        {[-.58, -.29, 0, .29, .58].map(x => <group key={x} position={[x, 0, Math.abs(x) * .33]}
          scale={[1, x === 0 ? variation.height : 1 / variation.height, 1]}>
          <DetailMesh position={[0, .012, 0]} scale={[.16, .023, .35]}
            geometry={pool.geometry("box")} material={pool.standard(VISUAL.nuggetShade)} />
          {[-.12, 0, .12].map(z => <group key={z} position={[0, 0, z]}>
            <DetailMesh position={[0, .13, 0]} scale={[.022, .26, .022]}
              geometry={pool.geometry("box")} material={pool.standard(VISUAL.trunk)} />
            <DetailMesh position={[0, .28, 0]} rotation={[0, 0, x * .18 + z * .25]} scale={[.065, .14, .065]} castShadow
              geometry={pool.geometry("rock")} material={pool.standard(VISUAL.wheat)} />
          </group>)}
        </group>)}
      </group>;
}

export function PastureVisual(_: Props) {
  const pool = useVisualResources();
  return <><Sheep x={-.4} z={-.4} rotation={.3} /><Sheep x={.3} z={-.55} scale={.8} rotation={-.6} />
        <Sheep x={.62} z={-.02} scale={.62} rotation={1.2} />
        <DetailMesh position={[-.63, TILE_TOP + .025, -.12]} scale={[.08, .05, .065]} geometry={pool.geometry("rock")} material={pool.standard(VISUAL.peak)} />
        {[[-.64, .12], [-.06, -.69], [.55, .45], [-.48, .52]].map(([x, z], i) => <group key={i} position={[x, TILE_TOP, z]}>
          <DetailMesh position={[0, .035, 0]} scale={[.055, .07, .055]}
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.treeLight)} />
          <DetailMesh position={[.06, .025, .03]} scale={[.04, .05, .04]}
            geometry={pool.geometry("cone")} material={pool.standard(VISUAL.tree)} />
        </group>)}</>;
}
