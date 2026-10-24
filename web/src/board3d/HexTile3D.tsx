import { memo } from "react";
import { tileFeedback } from "./materials";
import NumberToken3D from "./NumberToken3D";
import TerrainHexVisual from "./TerrainHexVisual";
import { TILE_TOP } from "./coordinates";
import { ignoreTerrainRaycast } from "./terrainAssets";
import { useVisualResources } from "./VisualResources";
import type { RenderTile } from "./types";
import { publicTileVisual } from "../board/publicTiles";
import { FogHexVisual, FogRevealVisual } from "./FogVisual";
import type { TerrainDetail } from "./terrainProportions";

export default memo(function HexTile3D({ tile, hovered, legal, selected, reveal, robberClearance = false, detail = "current", onHover, onInspect }: {
  tile: RenderTile; hovered: boolean; legal: boolean; selected: boolean;
  reveal?: number;
  robberClearance?: boolean;
  detail?: TerrainDetail;
  onHover: (tileIndex: number | null) => void;
  onInspect: (tileIndex: number) => void;
}) {
  const pool = useVisualResources();
  const visual = publicTileVisual(tile);
  const hidden = visual.visibility === "hidden";
  const feedback = tileFeedback(hovered, legal && !hidden, selected && !hidden);
  return <group position={tile.position} userData={{ tileIndex: tile.tileIndex, ...visual, legal: legal && !hidden, selected: selected && !hidden }}
    onPointerOver={e => { e.stopPropagation(); onHover(tile.tileIndex); }}
    onPointerOut={() => onHover(null)}
    onClick={e => { e.stopPropagation(); if (e.delta < 5 && !hidden) onInspect(tile.tileIndex); }}>
    <mesh geometry={pool.geometry("hex")} material={pool.flat("#ffffff", 0)}
      userData={{ tileIndex: tile.tileIndex }} />
    {hidden ? <FogHexVisual /> : <TerrainHexVisual terrain={visual.terrain} tileIndex={tile.tileIndex} robberClearance={robberClearance} detail={detail} />}
    {feedback && <mesh position={[0, TILE_TOP + .015, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 6]}
      geometry={pool.ring(.93, .98, 6)} material={pool.flat(feedback.color, selected ? .9 : hovered ? .8 : .3, true)}
      renderOrder={5} raycast={ignoreTerrainRaycast} />}
    {visual.number != null && <NumberToken3D number={visual.number} robberClearance={robberClearance && !hidden} />}
    {!hidden && reveal != null && <FogRevealVisual started={reveal} />}
  </group>;
});
