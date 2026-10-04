import { useMemo } from "react";
import { SRGBColorSpace } from "three";
import { TILE_TOP } from "./coordinates";

/** Canvas-generated label: no font download or external texture assets. */
export function TokenLabel({ text, color = "#263442", width = 0.58, depth = 0.58 }: {
  text: string; color?: string; width?: number; depth?: number;
}) {
  const canvas = useMemo(() => {
    const image = document.createElement("canvas");
    image.width = 256;
    image.height = 256;
    const context = image.getContext("2d");
    if (context) {
      context.fillStyle = color;
      context.textAlign = "center";
      context.textBaseline = "middle";
      const lines = text.split("\n");
      lines.forEach((line, index) => {
        context.font = `700 ${lines.length === 1 ? 150 : index === 0 ? 100 : 52}px Arial, sans-serif`;
        context.fillText(line, 128, lines.length === 1 ? 135 : 88 + index * 95);
      });
    }
    return image;
  }, [text, color]);
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[width, depth]} />
      <meshBasicMaterial transparent toneMapped={false} depthWrite={false}>
        <canvasTexture attach="map" args={[canvas]} colorSpace={SRGBColorSpace} />
      </meshBasicMaterial>
    </mesh>
  );
}

export default function NumberToken3D({ number }: { number: number }) {
  const highlighted = number === 6 || number === 8;
  return (
    <group position={[0, TILE_TOP + 0.055, 0]} userData={{ number }}>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[0.34, 0.34, 0.08, 32]} />
        <meshStandardMaterial color={highlighted ? "#fff2df" : "#fffdf5"} roughness={0.85} />
      </mesh>
      <group position={[0, 0.042, 0]}>
        <TokenLabel text={String(number)} color={highlighted ? "#c23b33" : "#263442"} />
      </group>
    </group>
  );
}
