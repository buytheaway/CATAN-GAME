import { memo } from "react";
import { tileFeedback, terrainStyle } from "./materials";
import NumberToken3D from "./NumberToken3D";
import TerrainHints from "./TerrainHints";
import { useVisualResources } from "./VisualResources";
import type { RenderTile } from "./types";

export default memo(function HexTile3D({ tile, hovered, legal, selected, onHover, onInspect }: {
  tile: RenderTile; hovered: boolean; legal: boolean; selected: boolean;
  onHover: (tileIndex: number | null) => void;
  onInspect: (tileIndex: number) => void;
}) {
  const style = terrainStyle(tile.terrain);
  const pool = useVisualResources();
  return <group position={tile.position} userData={{ tileIndex: tile.tileIndex, terrain: tile.terrain, legal, selected }}
    onPointerOver={e => { e.stopPropagation(); onHover(tile.tileIndex); }}
    onPointerOut={() => onHover(null)}
    onClick={e => { e.stopPropagation(); if (e.delta < 5) onInspect(tile.tileIndex); }}>
    <mesh geometry={pool.geometry("hex")} material={[pool.standard(style.color, false, tileFeedback(hovered, legal, selected)), pool.standard(style.side)]}
      receiveShadow castShadow userData={{ tileIndex: tile.tileIndex }} />
    <TerrainHints terrain={tile.terrain} tileIndex={tile.tileIndex} />
    {tile.number != null && <NumberToken3D number={tile.number} />}
  </group>;
});
