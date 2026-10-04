import { portAppearance, VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";
import { TokenLabel } from "./NumberToken3D";
import type { RenderPort } from "./types";

export default function Port3D({ port }: { port: RenderPort }) {
  const style = portAppearance(port.kind);
  const pool = useVisualResources();
  const dx = port.position[0] - port.anchor[0];
  const dz = port.position[2] - port.anchor[2];
  return (
    <group userData={{ edge: port.edge, kind: port.kind }}>
      <mesh position={[(port.anchor[0] + port.position[0]) / 2, 0.16, (port.anchor[2] + port.position[2]) / 2]}
        rotation={[0, -Math.atan2(dz, dx), 0]} scale={[Math.hypot(dx, dz), 0.08, 0.22]} receiveShadow
        geometry={pool.geometry("box")} material={pool.standard(VISUAL.dock)} />
      <group position={port.position}>
        <mesh receiveShadow castShadow scale={[0.45, 0.075, 0.45]}
          geometry={pool.geometry("cylinder")} material={pool.standard(style.color)} />
        <mesh position={[0, 0.039, 0]} scale={[0.39, 0.012, 0.39]}
          geometry={pool.geometry("cylinder")} material={pool.standard(VISUAL.ivory)} />
        <group position={[0, 0.047, 0]}><TokenLabel text={style.label.toUpperCase()} width={0.73} depth={0.73} /></group>
      </group>
    </group>
  );
}
