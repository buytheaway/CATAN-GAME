import { TILE_TOP } from "../coordinates";
import { terrainVariation } from "../materials";
import { useVisualResources } from "../VisualResources";
import { DetailMesh } from "./Details";
import { waterStyle, type WaterAppearance } from "../waterMaterials";
type Props = { variation: ReturnType<typeof terrainVariation>; waterAppearance?: WaterAppearance };

export function SeaVisual({ waterAppearance = "current" }: Props) {
  const pool = useVisualResources();
  return <group position={[-0.24, TILE_TOP + 0.014, -0.2]}>
        {[0, 1, 2, 3, 4].map(i => <DetailMesh key={i} position={[-.22 + i % 3 * .25, 0, -.15 + Math.floor(i / 3) * .35]}
          rotation={[0, -.35 + i % 2 * .15, 0]}
          geometry={pool.geometry("wave")} material={pool.flat(waterStyle(waterAppearance).fallbackWave, 0.55)} />)}
      </group>;
}
