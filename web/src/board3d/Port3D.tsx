import { portAppearance } from "./materials";
import { TokenLabel } from "./NumberToken3D";
import type { RenderPort } from "./types";

export default function Port3D({ port }: { port: RenderPort }) {
  const style = portAppearance(port.kind);
  const dx = port.position[0] - port.anchor[0];
  const dz = port.position[2] - port.anchor[2];
  return (
    <group userData={{ edge: port.edge, kind: port.kind }}>
      <mesh position={[(port.anchor[0] + port.position[0]) / 2, 0.18, (port.anchor[2] + port.position[2]) / 2]} rotation={[0, -Math.atan2(dz, dx), 0]} receiveShadow>
        <boxGeometry args={[Math.hypot(dx, dz), 0.08, 0.18]} />
        <meshStandardMaterial color="#b6a181" roughness={1} />
      </mesh>
      <group position={port.position}>
        <mesh receiveShadow castShadow>
          <cylinderGeometry args={[0.36, 0.36, 0.09, 24]} />
          <meshStandardMaterial color={style.color} roughness={0.9} />
        </mesh>
        <group position={[0, 0.047, 0]}><TokenLabel text={style.label} width={0.65} depth={0.65} /></group>
      </group>
    </group>
  );
}
