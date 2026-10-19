import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { DirectionalLight, PCFSoftShadowMap } from "three";
import CameraRig from "./CameraRig";
import HexTile3D from "./HexTile3D";
import Port3D from "./Port3D";
import { City3D, Road3D, Settlement3D } from "./Pieces3D";
import { createRenderModel } from "./model";
import type { BoardBounds, BoardRenderModel, BoardSnapshot } from "./types";
import type { BoardInteraction } from "../board/interaction";
import InteractionOverlay3D from "./InteractionOverlay3D";
import { VisualResources, useVisualResources } from "./VisualResources";
import { VISUAL } from "./materials";
import { cameraFootprint, coastVisualPosition } from "./coordinates";
import GameIcon from "../game/GameIcon";
import DiceRoll3D from "./DiceRoll3D";
import type { DiceRollVisual } from "../game/dice";
import { colorForPlayer } from "../board/colors";
import DecorativeOcean from "./DecorativeOcean";
import AmbientShips from "./AmbientShips";
import { decorativeShipsEnabled, oceanClearance } from "./environment";
import { buildPreview, replacesSettlement } from "./preview";
import type { PieceCue } from "./pieceFeedback";
import { edgeId } from "../board/constants";
import { FogPresentation } from "./FogVisual";
import type { FogQuality } from "./fogPresentation";
import { useReducedMotion } from "../game/motion";
import { SceneMotion } from "./SceneMotion";
import ShipFleet3D from "./ShipFleet3D";
import type { ShipCue } from "../board/shipFeedback";
import type { ThreatCue } from "../board/threatFeedback";
import Threats3D from "./Threats3D";
import type { ShipModel } from "./shipAssets";

const ignoreRaycast = () => undefined;
function Coastline({ coast }: Pick<BoardRenderModel, "coast">) {
  const pool = useVisualResources();
  return <>{coast.map(c => <mesh key={c.edge.join(",")} position={coastVisualPosition(c.position)} rotation={[0, c.rotation, 0]}
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

export default function Board3D({ state, interaction, diceRoll, matchKey = "", connected = true, reveals,
  shipCues = new Map(), shipsAnimated = true, onShipsAnimated,
  pieceCues = new Map(), constructionAnimated = true, onConstructionAnimated,
  threatCues = new Map(), threatsAnimated = true, onThreatsAnimated,
  shipModel = "procedural", onShipModel }: {
  state: BoardSnapshot; interaction: BoardInteraction; diceRoll?: DiceRollVisual | null;
  matchKey?: string; connected?: boolean;
  reveals?: ReadonlyMap<number, number>;
  shipCues?: ReadonlyMap<string, ShipCue>; shipsAnimated?: boolean; onShipsAnimated?: (enabled: boolean) => void;
  pieceCues?: ReadonlyMap<string, PieceCue>; constructionAnimated?: boolean; onConstructionAnimated?: (enabled: boolean) => void;
  threatCues?: ReadonlyMap<string, ThreatCue>; threatsAnimated?: boolean; onThreatsAnimated?: (enabled: boolean) => void;
  shipModel?: ShipModel; onShipModel?: (model: ShipModel) => void;
}) {
  const model = useMemo(() => createRenderModel(state), [state]);
  const [hoveredTile, setHoveredTile] = useState<number | null>(null);
  const [targetHover, setTargetHover] = useState<string | null>(null);
  const preview = buildPreview(state, interaction, targetHover);
  useEffect(() => { setTargetHover(null); }, [interaction.action, interaction.selection.waiting, connected, matchKey]);
  const [resetVersion, setResetVersion] = useState(0);
  const [fogQuality, setFogQuality] = useState<FogQuality>("mist");
  const reduced = useReducedMotion();
  const construction = constructionAnimated && connected && !reduced ? pieceCues : new Map<string, PieceCue>();
  const hidden = model.tiles.some(tile => tile.visibility === "hidden");
  const shipColors = useMemo(() => new Map(model.ships.map(ship => [ship.owner, colorForPlayer(ship.owner, state.players)])),
    [model.ships, state.players]);
  const publicPositions = useMemo(() => new Map(model.tiles.filter(tile => tile.visibility === "revealed")
    .map(tile => [tile.tileIndex, tile.position])), [model.tiles]);
  const hover = useCallback((tileIndex: number | null) => setHoveredTile(tileIndex), []);
  const inspect = useCallback((tileIndex: number) => {
    interaction.onTileClick(tileIndex);
  }, [interaction.onTileClick]);
  const { bounds } = model;
  const footprint = JSON.stringify(cameraFootprint(model));

  return (
    <div className="board3d" data-renderer="3d" data-tile-count={model.tiles.length}
      data-selectable={hoveredTile != null && model.tiles[hoveredTile]?.visibility === "revealed" && interaction.targets.tiles.includes(hoveredTile)}>
      <div className="board3d-toolbar">
        {hidden && <label className="board3d-fog-quality">Fog
          <select aria-label="Fog effects" value={fogQuality} onChange={e => setFogQuality(e.target.value as FogQuality)}>
            <option value="mist">Mist{reduced ? " · still" : " · animated"}</option>
            <option value="still">Mist · still</option>
            <option value="simple">Simple</option>
          </select>
        </label>}
        {!!model.ships.length && onShipsAnimated && <label className="board3d-ship-quality">Ships
          <select aria-label="Ship effects" value={shipsAnimated ? "motion" : "static"}
            onChange={e => onShipsAnimated(e.target.value === "motion")}>
            <option value="motion">{reduced ? "Still · reduced motion" : "Motion"}</option>
            <option value="static">Still</option>
          </select>
        </label>}
        {onShipModel && <label className="board3d-ship-model">Ship model
          <select aria-label="Ship model" value={shipModel} onChange={e => onShipModel(e.target.value as ShipModel)}>
            <option value="procedural">Procedural</option>
            <option value="glb">GLB · pilot</option>
          </select>
        </label>}
        {onConstructionAnimated && <label className="board3d-construction-quality">Construction
          <select aria-label="Construction effects" value={constructionAnimated ? "motion" : "static"}
            onChange={e => onConstructionAnimated(e.target.value === "motion")}>
            <option value="motion">{reduced ? "Still · reduced motion" : "Motion"}</option>
            <option value="static">Still</option>
          </select>
        </label>}
        {onThreatsAnimated && <label className="board3d-threat-quality">Robber / pirate
          <select aria-label="Robber & pirate effects" value={threatsAnimated ? "motion" : "static"}
            onChange={e => onThreatsAnimated(e.target.value === "motion")}>
            <option value="motion">{reduced ? "Still · reduced motion" : "Motion"}</option>
            <option value="static">Still</option>
          </select>
        </label>}
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
          <SceneMotion reduced={reduced} connected={connected}>
          <FogPresentation quality={fogQuality} reduced={reduced} connected={connected} hidden={hidden}>
          <DecorativeOcean bounds={bounds} coast={model.coast} />
          {decorativeShipsEnabled(state) && <AmbientShips center={bounds.center} clearance={oceanClearance(model)} />}
          {diceRoll && <DiceRoll3D key={diceRoll.id} roll={diceRoll} center={bounds.center} />}
          {model.tiles.map(t => <HexTile3D key={t.tileIndex} tile={t} hovered={hoveredTile === t.tileIndex}
            legal={interaction.targets.tiles.includes(t.tileIndex)} selected={interaction.selection.victim?.tile === t.tileIndex}
            reveal={reveals?.get(t.tileIndex)} onHover={hover} onInspect={inspect} />)}
          <Coastline coast={model.coast} />
          {model.roads.map(road => <Road3D key={road.edge.join(",")} road={road} color={colorForPlayer(road.owner, state.players)}
            cue={construction.get(`e:${edgeId(road.edge)}`)} />)}
          <ShipFleet3D ships={model.ships} cues={shipCues} vertices={state.vertices} edges={state.edges} size={state.size}
            colors={shipColors} moving={shipsAnimated && connected && !reduced} model={shipModel} />
          {model.buildings.map(building => building.level === 1
            ? <Settlement3D key={building.vertexId} building={building} color={colorForPlayer(building.owner, state.players)}
                cue={construction.get(`v:${building.vertexId}`)} visible={!replacesSettlement(preview, building)} />
            : <City3D key={building.vertexId} building={building} color={colorForPlayer(building.owner, state.players)}
                cue={construction.get(`v:${building.vertexId}`)} />)}
          {model.ports.map(port => <Port3D key={port.edge.join(",")} port={port} />)}
          <Threats3D robbers={model.robbers} pirate={model.pirate} positions={publicPositions} cues={threatCues}
            moving={threatsAnimated && connected && !reduced} />
          <InteractionOverlay3D state={state} interaction={interaction} hover={targetHover} onHover={setTargetHover} shipModel={shipModel} />
          </FogPresentation>
          </SceneMotion>
          </VisualResources>
        </Canvas>
      </div>
    </div>
  );
}
