import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { DirectionalLight, PCFSoftShadowMap } from "three";
import CameraRig from "./CameraRig";
import HexTile3D from "./HexTile3D";
import Port3D from "./Port3D";
import { City3D, Pirate3D, Road3D, Robber3D, Settlement3D, Ship3D } from "./Pieces3D";
import { createRenderModel } from "./model";
import type { BoardBounds, BoardSnapshot } from "./types";

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
    intensity={2.4} castShadow shadow-mapSize={[1024, 1024]}
    shadow-camera-left={-reach} shadow-camera-right={reach} shadow-camera-top={reach} shadow-camera-bottom={-reach}
    shadow-camera-far={reach * 4} shadow-bias={-0.0005} shadow-normalBias={0.025} />;
}

export default function Board3D({ state }: { state: BoardSnapshot }) {
  const model = useMemo(() => createRenderModel(state), [state]);
  const [hoveredTile, setHoveredTile] = useState<number | null>(null);
  const [inspectedTile, setInspectedTile] = useState<number | null>(null);
  const [resetVersion, setResetVersion] = useState(0);
  const hover = useCallback((tileIndex: number | null) => setHoveredTile(tileIndex), []);
  const inspect = useCallback((tileIndex: number) => setInspectedTile(tileIndex), []);
  const visibleTile = hoveredTile ?? inspectedTile;
  const tile = visibleTile != null ? state.tiles[visibleTile] : null;
  const { bounds } = model;

  return (
    <div className="board3d" data-renderer="3d" data-tile-count={model.tiles.length}>
      <div className="board3d-toolbar">
        <span>Drag to orbit · Scroll to zoom</span>
        <button type="button" className="btn" onClick={() => setResetVersion(v => v + 1)}>Reset Camera</button>
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
          <color attach="background" args={["#dce9ed"]} />
          <ambientLight intensity={1.3} />
          <BoardLight bounds={bounds} />
          <CameraRig bounds={bounds} resetVersion={resetVersion} />
          <mesh position={[bounds.center[0], -0.025, bounds.center[2]]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
            <planeGeometry args={[bounds.width + 2, bounds.depth + 2]} />
            <meshStandardMaterial color="#c6dce1" roughness={1} />
          </mesh>
          {model.tiles.map(t => <HexTile3D key={t.tileIndex} tile={t} hovered={hoveredTile === t.tileIndex} onHover={hover} onInspect={inspect} />)}
          {model.roads.map(road => <Road3D key={road.edge.join(",")} road={road} />)}
          {model.ships.map(ship => <Ship3D key={ship.edge.join(",")} ship={ship} />)}
          {model.buildings.map(building => building.level === 1
            ? <Settlement3D key={building.vertexId} building={building} />
            : <City3D key={building.vertexId} building={building} />)}
          {model.ports.map(port => <Port3D key={port.edge.join(",")} port={port} />)}
          {model.robbers.map((robber, i) => <Robber3D key={i} {...robber} />)}
          {model.pirate && <Pirate3D {...model.pirate} />}
        </Canvas>
      </div>
      <div className="board3d-footer">
        <span>View only · Use 2D to place pieces or move the robber/pirate.</span>
        <span aria-live="polite">{tile ? `Tile ${visibleTile} · ${tile.terrain}${tile.number != null ? ` · ${tile.number}` : ""}` : "Hover or click a hex to inspect it."}</span>
      </div>
    </div>
  );
}
