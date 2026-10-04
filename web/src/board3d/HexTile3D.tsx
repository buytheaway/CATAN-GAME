import { memo } from "react";
import { TILE_TOP } from "./coordinates";
import { terrainStyle } from "./materials";
import NumberToken3D from "./NumberToken3D";
import TerrainHints from "./TerrainHints";
import type { RenderTile } from "./types";

export default memo(function HexTile3D({ tile, hovered, onHover, onInspect }: {
  tile: RenderTile;
  hovered: boolean;
  onHover: (tileIndex: number | null) => void;
  onInspect: (tileIndex: number) => void;
}) {
  const style = terrainStyle(tile.terrain);
  return (
    <group position={tile.position} userData={{ tileIndex: tile.tileIndex, terrain: tile.terrain }}
      onPointerOver={event => { event.stopPropagation(); onHover(tile.tileIndex); }}
      onPointerOut={() => onHover(null)}
      onClick={event => { event.stopPropagation(); if (event.delta < 5) onInspect(tile.tileIndex); }}
    >
      <mesh position={[0, 0.14, 0]} receiveShadow castShadow>
        <cylinderGeometry args={[0.98, 0.98, 0.2, 6]} />
        <meshStandardMaterial color={style.side} roughness={0.9} />
      </mesh>
      <mesh
        position={[0, TILE_TOP - 0.025, 0]}
        receiveShadow
        userData={{ tileIndex: tile.tileIndex }}
      >
        <cylinderGeometry args={[0.96, 0.96, 0.05, 6]} />
        <meshStandardMaterial color={style.color} roughness={0.86} emissive={hovered ? "#b9d9e7" : "#000000"} emissiveIntensity={hovered ? 0.25 : 0} />
      </mesh>
      <TerrainHints terrain={tile.terrain} />
      {tile.number != null && <NumberToken3D number={tile.number} />}
    </group>
  );
});
