import { portAppearance, VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";
import { TokenLabel } from "./NumberToken3D";
import type { RenderPort } from "./types";
import { portLabelPosition } from "./coordinates";

export default function Port3D({ port }: { port: RenderPort }) {
  const style = portAppearance(port.kind);
  const pool = useVisualResources();
  const position = portLabelPosition(port);
  const dx = position[0] - port.anchor[0];
  const dz = position[2] - port.anchor[2];
  const dockRotation = -Math.atan2(dz, dx);
  // Follow the supplied edge, keeping text upright from the default camera side.
  const labelRotation = port.rotation - Math.round(port.rotation / Math.PI) * Math.PI;
  return (
    <group userData={{ edge: port.edge, kind: port.kind }}>
      <group position={[(port.anchor[0] + position[0]) / 2, 0.16, (port.anchor[2] + position[2]) / 2]}
        rotation={[0, dockRotation, 0]}>
        <mesh scale={[Math.hypot(dx, dz), 0.08, 0.15]} receiveShadow castShadow
          geometry={pool.geometry("box")} material={pool.standard(VISUAL.trunk)} />
        {[-0.13, 0, 0.13].map(x => <mesh key={x} position={[x, 0.048, 0]} scale={[0.09, 0.025, 0.23]} receiveShadow
          geometry={pool.geometry("box")} material={pool.standard(VISUAL.dock)} />)}
      </group>
      <group position={position} rotation={[0, labelRotation, 0]}>
        <mesh receiveShadow castShadow geometry={pool.geometry("port")}
          material={pool.standard(port.kind.includes("3:1") ? VISUAL.dock : style.color)} />
        <mesh position={[0, 0.068, 0]} scale={[0.57, 0.012, 0.4]}
          geometry={pool.geometry("box")} material={pool.standard("#29414c")} />
        <group position={[0, 0.076, 0]}><TokenLabel text={style.label.toUpperCase()} color="#f0e7d3" width={0.55} depth={0.39} /></group>
      </group>
    </group>
  );
}
