import { memo } from "react";
import { TILE_TOP } from "./coordinates";
import { targetColor, terrainStyle } from "./materials";
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
    <mesh geometry={pool.geometry("hex")} material={[pool.standard(style.color), pool.standard(style.side)]}
      receiveShadow castShadow userData={{ tileIndex: tile.tileIndex }} />
    {(hovered || legal || selected) && <mesh position={[0, TILE_TOP + 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]}
      geometry={pool.ring(selected ? 0.85 : 0.9, 0.935, 6)}
      material={pool.flat(targetColor(hovered, selected), hovered || selected ? 0.95 : 0.58)} />}
    <TerrainHints terrain={tile.terrain} />
    {tile.number != null && <NumberToken3D number={tile.number} />}
  </group>;
});