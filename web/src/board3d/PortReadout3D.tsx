import { useMemo } from "react";
import { SRGBColorSpace } from "three";
import { RESOURCE_ICON_PATHS } from "../game/resourceIcons";
import { portAppearance, VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";
import { ignoreSceneryRaycast } from "./environment";

/** Round printed harbour token, using the exact card/bank icon paths. No game hit target. */
export default function PortReadout3D({ kind }: { kind: string }) {
  const pool = useVisualResources();
  const { label, resource, color } = portAppearance(kind);
  const canvas = useMemo(() => {
    const image = document.createElement("canvas");
    image.width = image.height = 256;
    const ctx = image.getContext("2d");
    if (!ctx) return image;
    ctx.fillStyle = VISUAL.ivory;
    ctx.beginPath(); ctx.arc(128, 128, 126, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = color; ctx.lineWidth = 10;
    ctx.beginPath(); ctx.arc(128, 128, 119, 0, Math.PI * 2); ctx.stroke();
    if (resource) {
      ctx.save(); ctx.translate(84, 36); ctx.scale(3.65, 3.65);
      ctx.strokeStyle = color; ctx.lineWidth = 1.9; ctx.lineCap = "round"; ctx.lineJoin = "round";
      RESOURCE_ICON_PATHS[resource].forEach(d => ctx.stroke(new Path2D(d)));
      ctx.restore();
    }
    ctx.fillStyle = VISUAL.ink; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = `700 ${resource ? 78 : 92}px Arial, sans-serif`;
    ctx.fillText(label, 128, resource ? 177 : 132);
    return image;
  }, [label, resource, color]);
  return <group position={[0, .075, 0]} userData={{ portReadout: true, ratio: label, resource }}>
    <mesh scale={[.36, .055, .36]} raycast={ignoreSceneryRaycast}
      geometry={pool.geometry("cylinder")} material={pool.standard(color)} receiveShadow castShadow />
    <mesh position={[0, .03, 0]} scale={[.35, .35, 1]} rotation={[-Math.PI / 2, 0, 0]}
      geometry={pool.geometry("disc")} raycast={ignoreSceneryRaycast}>
      <meshBasicMaterial toneMapped={false}><canvasTexture attach="map" args={[canvas]} colorSpace={SRGBColorSpace} /></meshBasicMaterial>
    </mesh>
  </group>;
}
