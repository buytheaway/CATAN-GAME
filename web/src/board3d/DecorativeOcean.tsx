import type { BoardBounds, BoardRenderModel } from "./types";
import { useVisualResources } from "./VisualResources";
import { VISUAL } from "./materials";
import { ignoreSceneryRaycast } from "./environment";

const ignoreRaycast = ignoreSceneryRaycast;

/** Table scenery, not gameplay tiles. Static and excluded from framing/legal topology. */
export default function DecorativeOcean({ bounds, coast }: { bounds: BoardBounds; coast: BoardRenderModel["coast"] }) {
  const pool = useVisualResources();
  const canvas = useMemo(() => {
    const image = document.createElement("canvas"); image.width = image.height = 1024;
    const ctx = image.getContext("2d");
    if (!ctx) return image;
    const depth = ctx.createRadialGradient(512, 512, 0, 512, 512, 724);
    depth.addColorStop(0, "#286479"); depth.addColorStop(.2, "#1a4e64");
    depth.addColorStop(.5, "#153a4e"); depth.addColorStop(1, VISUAL.background);
    ctx.fillStyle = depth; ctx.fillRect(0, 0, 1024, 1024);
    ctx.lineWidth = 1.5; ctx.strokeStyle = "#9dcbd01c";
    for (let i = 0; i < 180; i++) {
      const x = (i * 239 + 71) % 1024, y = (i * 389 + 31) % 1024;
      const width = 14 + i % 5 * 5;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.quadraticCurveTo(x + width / 2, y + 3, x + width, y); ctx.stroke();
    }
    return image;
  }, []);
  return <group userData={{ decorativeOcean: true }}>
    <mesh position={[bounds.center[0], -.032, bounds.center[2]]} scale={[bounds.width * 4, bounds.depth * 4, 1]}
      rotation={[-Math.PI / 2, 0, 0]} raycast={ignoreRaycast} geometry={pool.geometry("plane")}>
      <meshBasicMaterial toneMapped={false}><canvasTexture attach="map" args={[canvas]} colorSpace={SRGBColorSpace} /></meshBasicMaterial>
    </mesh>
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
import { useMemo } from "react";
import { SRGBColorSpace } from "three";
