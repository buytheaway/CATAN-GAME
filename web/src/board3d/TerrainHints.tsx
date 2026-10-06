import { terrainVariation } from "./materials";
import { ForestVisual, FieldsVisual, PastureVisual } from "./terrain/Vegetation";
import { HillsVisual, MountainsVisual, DesertVisual, GoldVisual } from "./terrain/Landforms";
import { SeaVisual } from "./terrain/Sea";
const visuals: Record<string, typeof ForestVisual> = { forest: ForestVisual, fields: FieldsVisual, pasture: PastureVisual, hills: HillsVisual, mountains: MountainsVisual, desert: DesertVisual, gold: GoldVisual, sea: SeaVisual };

/** Static local decoration; original centers, indices and board topology stay untouched. */
export default function TerrainHints({ terrain, tileIndex }: { terrain: string; tileIndex: number }) {
  const variation = terrainVariation(tileIndex);
  const Visual = visuals[terrain];
  return <group rotation={[0, terrain === "sea" ? 0 : variation.rotation, 0]}
    position={[terrain === "sea" ? 0 : variation.offset, 0, 0]}
    scale={terrain === "sea" ? [1, 1, 1] : [variation.scale, 1, variation.scale]}>
    {Visual && <Visual variation={variation} />}
  </group>;
}
