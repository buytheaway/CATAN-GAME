import { useMemo } from "react";
import { SRGBColorSpace } from "three";
import { TILE_TOP } from "./coordinates";
import { VISUAL } from "./materials";
import { useVisualResources } from "./VisualResources";

/** Canvas-generated label: no font download or external texture assets. */
export function TokenLabel({ text, color = VISUAL.ink, width = 0.72, depth = 0.72, pips = 0 }: {
  text: string; color?: string; width?: number; depth?: number; pips?: number;
}) {
  const pool = useVisualResources();
  const canvas = useMemo(() => {
    const image = document.createElement("canvas");
    image.width = 512;
    image.height = 512;
    const context = image.getContext("2d");
    if (context) {
      context.fillStyle = color;
      context.textAlign = "center";
      context.textBaseline = "middle";
      const lines = text.split("\n");
      lines.forEach((line, index) => {
        context.font = `700 ${lines.length === 1 ? 320 : index === 0 ? 230 : 92}px Arial, sans-serif`;
        context.fillText(line, 256, lines.length === 1 ? pips ? 228 : 260 : 182 + index * 180);
      });
      for (let i = 0; i < pips; i++) {
        context.beginPath();
        context.arc(256 + (i - (pips - 1) / 2) * 38, 410, 12, 0, Math.PI * 2);
        context.fill();
      }
    }
    return image;
  }, [text, color, pips]);
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} scale={[width, depth, 1]} geometry={pool.geometry("plane")}>
      <meshBasicMaterial transparent toneMapped={false} depthWrite={false}>
        <canvasTexture attach="map" args={[canvas]} colorSpace={SRGBColorSpace} />
      </meshBasicMaterial>
    </mesh>
  );
}

export default function NumberToken3D({ number }: { number: number }) {
  const highlighted = number === 6 || number === 8;
  const pool = useVisualResources();
  // Printed board-token dots, purely visual (never a production/roll calculation).
  const pips = Math.max(0, 6 - Math.abs(7 - number));
  return (
    <group position={[0, TILE_TOP + 0.045, 0.18]} userData={{ number }}>
      <mesh castShadow receiveShadow scale={[0.41, 0.075, 0.41]}
        geometry={pool.geometry("cylinder")} material={pool.standard(VISUAL.tokenSide)} />
      <mesh position={[0, 0.038, 0]} scale={[0.395, 0.012, 0.395]}
        geometry={pool.geometry("cylinder")} material={pool.standard(VISUAL.ivory)} />
      <group position={[0, 0.047, 0]}>
        <TokenLabel text={String(number)} color={highlighted ? VISUAL.accent : VISUAL.ink} pips={pips} />
      </group>
    </group>
  );
}
