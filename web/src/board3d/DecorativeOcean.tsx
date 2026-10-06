import type { BoardBounds, BoardRenderModel } from "./types";
import { useVisualResources } from "./VisualResources";
import { VISUAL } from "./materials";

const ignoreRaycast = () => undefined;

/** Table scenery, not gameplay tiles. Static and excluded from framing/legal topology. */
export default function DecorativeOcean({ bounds, coast }: { bounds: BoardBounds; coast: BoardRenderModel["coast"] }) {
  const pool = useVisualResources();
  return <group userData={{ decorativeOcean: true }}>
    <mesh position={[bounds.center[0], -.05, bounds.center[2]]} scale={[bounds.width * 4, .035, bounds.depth * 4]}
      receiveShadow raycast={ignoreRaycast} geometry={pool.geometry("box")} material={pool.standard("#153d50")} />
    {coast.map(c => <group key={c.edge.join(",")} position={[c.position[0], .055, c.position[2]]} rotation={[0, c.rotation, 0]}>
      <mesh scale={[c.length, .025, .21]} raycast={ignoreRaycast} geometry={pool.geometry("box")} material={pool.standard("#416b71")} />
      <mesh position={[0, .018, .11]} scale={[c.length * .8, .012, .035]} raycast={ignoreRaycast}
        geometry={pool.geometry("box")} material={pool.flat("#83a6a5", .6)} />
    </group>)}
    {Array.from({ length: 28 }, (_, i) => {
      const angle = i * Math.PI * 2 / 28, radius = bounds.radius * (1.03 + i % 3 * .08);
      return <mesh key={i} position={[bounds.center[0] + Math.cos(angle) * radius, -.025, bounds.center[2] + Math.sin(angle) * radius]}
        rotation={[0, i * .37, 0]} scale={[1.2, 1, 1.2]} raycast={ignoreRaycast}
        geometry={pool.geometry("wave")} material={pool.flat(VISUAL.wave, .22)} />;
    })}
  </group>;
}
