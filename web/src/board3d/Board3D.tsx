import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { DirectionalLight, PCFSoftShadowMap } from "three";
import CameraRig from "./CameraRig";
import HexTile3D from "./HexTile3D";
import Port3D from "./Port3D";
import { City3D, Pirate3D, Road3D, Robber3D, Settlement3D, Ship3D } from "./Pieces3D";
import { createRenderModel } from "./model";
import type { BoardBounds, BoardRenderModel, BoardSnapshot } from "./types";
import type { BoardInteraction } from "../board/interaction";
import InteractionOverlay3D from "./InteractionOverlay3D";
import { VisualResources, useVisualResources } from "./VisualResources";
import { VISUAL } from "./materials";
import { cameraFootprint } from "./coordinates";
import GameIcon from "../game/GameIcon";
import DiceRoll3D from "./DiceRoll3D";
import type { DiceRollVisual } from "../game/dice";
import { colorForPlayer } from "../board/colors";
import DecorativeOcean from "./DecorativeOcean";
import AmbientShips from "./AmbientShips";
import { decorativeShipsEnabled, oceanClearance } from "./environment";

const ignoreRaycast = () => undefined;
function Coastline({ coast }: Pick<BoardRenderModel, "coast">) {
  const pool = useVisualResources();
  return <>{coast.map(c => <mesh key={c.edge.join(",")} position={c.position} rotation={[0, c.rotation, 0]}
    scale={[c.length, .05, .12]} receiveShadow raycast={ignoreRaycast} userData={{ coastEdge: c.edge }}
    geometry={pool.geometry("box")} material={pool.standard(VISUAL.sandShade)} />)}</>;
}

function BoardLight({ bounds }: { bounds: BoardBounds }) {
  const light = useRef<DirectionalLight>(null);
  const invalidate = useThree(s => s.invalidate);
  const [x, , z] = bounds.center;
  const reach = bounds.radius * 1.8;
  useEffect(() => {
    if (!light.current) return;
    light.current.target.position.set(x, 0, z);
    light.current.target.updateMatrixWorld();
    light.current.shadow.camera.updateProjectionMatrix();
    invalidate();
  }, [x, z, reach, invalidate]);
  return <directionalLight ref={light} position={[x - reach * 0.4, reach, z + reach * 0.5]}
    intensity={2.1} castShadow shadow-mapSize={[1024, 1024]}
    shadow-camera-left={-reach} shadow-camera-right={reach} shadow-camera-top={reach} shadow-camera-bottom={-reach}
    shadow-camera-far={reach * 4} shadow-bias={-0.0005} shadow-normalBias={0.025} />;
}

export default function Board3D({ state, interaction, diceRoll }: {
  state: BoardSnapshot; interaction: BoardInteraction; diceRoll?: DiceRollVisual | null;
}) {
  const model = useMemo(() => createRenderModel(state), [state]);
  const [hoveredTile, setHoveredTile] = useState<number | null>(null);
  const [resetVersion, setResetVersion] = useState(0);
  const hover = useCallback((tileIndex: number | null) => setHoveredTile(tileIndex), []);
  const inspect = useCallback((tileIndex: number) => {
    interaction.onTileClick(tileIndex);
  }, [interaction.onTileClick]);
  const { bounds } = model;
  const footprint = JSON.stringify(cameraFootprint(model));

  return (
    <div className="board3d" data-renderer="3d" data-tile-count={model.tiles.length}
      data-selectable={hoveredTile != null && interaction.targets.tiles.includes(hoveredTile)}>
      <div className="board3d-toolbar">
        <button type="button" className="game-button" aria-label="Reset Camera"
          title="Reset camera · Drag the board to orbit; scroll to zoom" onClick={() => setResetVersion(v => v + 1)}>
          <GameIcon name="reset" /> Reset
        </button>
      </div>
      <div className="board3d-canvas" role="img" aria-label="Experimental 3D game board">
        <Canvas
          shadows={{ type: PCFSoftShadowMap }}
          frameloop="demand"
          dpr={[1, 1.5]}
          camera={{ fov: 38 }}
          gl={{ antialias: true }}
          fallback={<div className="board3d-fallback">WebGL is unavailable. Use the 2D board.</div>}
        >
          <color attach="background" args={[VISUAL.background]} />
          <ambientLight intensity={0.85} />
          <hemisphereLight args={["#edf7ff", "#738176", 0.55]} />
          <BoardLight bounds={bounds} />
          <CameraRig bounds={bounds} footprint={footprint} resetVersion={resetVersion} />
          <mesh position={[bounds.center[0], 0, bounds.center[2]]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
            <planeGeometry args={[bounds.width * 4, bounds.depth * 4]} />
            <shadowMaterial transparent opacity={0.22} />
          </mesh>
          <VisualResources>
          <DecorativeOcean bounds={bounds} coast={model.coast} />
          {decorativeShipsEnabled(state) && <AmbientShips center={bounds.center} clearance={oceanClearance(model)} />}
          {diceRoll && <DiceRoll3D key={diceRoll.id} roll={diceRoll} center={bounds.center} />}
          {model.tiles.map(t => <HexTile3D key={t.tileIndex} tile={t} hovered={hoveredTile === t.tileIndex}
            legal={interaction.targets.tiles.includes(t.tileIndex)} selected={interaction.selection.victim?.tile === t.tileIndex}
            onHover={hover} onInspect={inspect} />)}
          <Coastline coast={model.coast} />
          {model.roads.map(road => <Road3D key={road.edge.join(",")} road={road} color={colorForPlayer(road.owner, state.players)} />)}
          {model.ships.map(ship => <Ship3D key={ship.edge.join(",")} ship={ship} color={colorForPlayer(ship.owner, state.players)} />)}
          {model.buildings.map(building => building.level === 1
            ? <Settlement3D key={building.vertexId} building={building} color={colorForPlayer(building.owner, state.players)} />
            : <City3D key={building.vertexId} building={building} color={colorForPlayer(building.owner, state.players)} />)}
          {model.ports.map(port => <Port3D key={port.edge.join(",")} port={port} />)}
          {model.robbers.map((robber, i) => <Robber3D key={i} {...robber} />)}
          {model.pirate && <Pirate3D {...model.pirate} />}
          <InteractionOverlay3D state={state} interaction={interaction} />
          </VisualResources>
        </Canvas>
      </div>
    </div>
  );
}
