import { VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";
import PortReadout3D from "./PortReadout3D";
import type { RenderPort } from "./types";
import { portConnectors, portLabelPosition, TILE_TOP } from "./coordinates";

const ignoreRaycast = () => undefined;

export default function Port3D({ port }: { port: RenderPort }) {
  const pool = useVisualResources();
  const position = portLabelPosition(port);
  return (
    <group userData={{ edge: port.edge, kind: port.kind }}>
      {portConnectors(port).map(path => <group key={path.vertexId} userData={{ portVertex: path.vertexId }}>
        <group position={[path.position[0], TILE_TOP + .015, path.position[2]]} rotation={[0, path.rotation, 0]}>
          <mesh scale={[path.length, .055, .105]} receiveShadow castShadow raycast={ignoreRaycast}
            geometry={pool.geometry("box")} material={pool.standard(VISUAL.dock)} />
          <mesh position={[0, .029, 0]} scale={[path.length, .012, .018]} raycast={ignoreRaycast}
            geometry={pool.geometry("box")} material={pool.standard(VISUAL.trunk)} />
        </group>
        <mesh position={[path.start[0], TILE_TOP + .025, path.start[2]]} scale={[.065, .075, .065]}
          raycast={ignoreRaycast} geometry={pool.geometry("cylinder")} material={pool.standard(VISUAL.ivory)} />
      </group>)}
      <group position={position}>
        <PortReadout3D kind={port.kind} />
      </group>
      <group position={[port.anchor[0], .12, port.anchor[2]]} rotation={[0, port.rotation, 0]} userData={{ decorativeHarbor: true }}>
        <mesh scale={[.3, .45, .65]} raycast={ignoreRaycast} geometry={pool.geometry("hull")} material={pool.standard(VISUAL.dock)} />
        <mesh position={[0, .11, 0]} scale={[.018, .23, .018]} raycast={ignoreRaycast}
          geometry={pool.geometry("box")} material={pool.standard(VISUAL.trunk)} />
        <mesh position={[.015, .1, 0]} scale={[.35, .35, .35]} raycast={ignoreRaycast}
          geometry={pool.geometry("sail")} material={pool.standard(VISUAL.ivory)} />
      </group>
    </group>
  );
}
