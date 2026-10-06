import { portAppearance, VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";
import { TokenLabel } from "./NumberToken3D";
import type { RenderPort } from "./types";
import { portConnectors, portLabelPosition, TILE_TOP } from "./coordinates";

const ignoreRaycast = () => undefined;

export default function Port3D({ port }: { port: RenderPort }) {
  const style = portAppearance(port.kind);
  const pool = useVisualResources();
  const position = portLabelPosition(port);
  // Follow the supplied edge, keeping text upright from the default camera side.
  const labelRotation = port.rotation - Math.round(port.rotation / Math.PI) * Math.PI;
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
      <group position={position} rotation={[0, labelRotation, 0]}>
        <mesh receiveShadow castShadow geometry={pool.geometry("port")}
          material={pool.standard(port.kind.includes("3:1") ? VISUAL.dock : style.color)} />
        <mesh position={[0, 0.068, 0]} scale={[0.57, 0.012, 0.4]}
          geometry={pool.geometry("box")} material={pool.standard("#29414c")} />
        <group position={[0, 0.076, 0]}><TokenLabel text={style.label.toUpperCase()} color="#f0e7d3" width={0.55} depth={0.39} /></group>
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
