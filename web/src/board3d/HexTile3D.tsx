import { memo } from "react";
import { tileFeedback } from "./materials";
import NumberToken3D from "./NumberToken3D";
import TerrainHexVisual from "./TerrainHexVisual";
import { TILE_TOP } from "./coordinates";
import { ignoreTerrainRaycast } from "./terrainAssets";
import { useVisualResources } from "./VisualResources";
import type { RenderTile } from "./types";

export default memo(function HexTile3D({ tile, hovered, legal, selected, onHover, onInspect }: {
  tile: RenderTile; hovered: boolean; legal: boolean; selected: boolean;
  onHover: (tileIndex: number | null) => void;
  onInspect: (tileIndex: number) => void;
}) {
  const pool = useVisualResources();
  const feedback = tileFeedback(hovered, legal, selected);
  return <group position={tile.position} userData={{ tileIndex: tile.tileIndex, terrain: tile.terrain, legal, selected }}
    onPointerOver={e => { e.stopPropagation(); onHover(tile.tileIndex); }}
    onPointerOut={() => onHover(null)}
    onClick={e => { e.stopPropagation(); if (e.delta < 5) onInspect(tile.tileIndex); }}>
    <mesh geometry={pool.geometry("hex")} material={pool.flat("#ffffff", 0)}
      userData={{ tileIndex: tile.tileIndex }} />
    <TerrainHexVisual terrain={tile.terrain} tileIndex={tile.tileIndex} />
    {feedback && <mesh position={[0, TILE_TOP + .015, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 6]}
      geometry={pool.ring(.93, .98, 6)} material={pool.flat(feedback.color, selected ? .9 : hovered ? .8 : .3, true)}
      renderOrder={5} raycast={ignoreTerrainRaycast} />}
    {tile.number != null && <NumberToken3D number={tile.number} />}
  </group>;
});
