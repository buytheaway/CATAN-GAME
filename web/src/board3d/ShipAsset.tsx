import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { Object3D } from "three";
import { cloneShipScene, loadShipAsset, shipAssetScale } from "./shipAssets";
import { useVisualResources } from "./VisualResources";

/** Body only: Ship3D/ShipFleet3D retain ownership, placement, previews and motion. */
export default function ShipAsset({ length, color, ghost, children }: {
  length: number; color: string; ghost: boolean; children: ReactNode;
}) {
  const [template, setTemplate] = useState<Object3D | null>(null);
  useEffect(() => {
    let mounted = true;
    loadShipAsset().then(source => { if (mounted) setTemplate(source); });
    return () => { mounted = false; };
  }, []);
  const pool = useVisualResources();
  const scene = useMemo(() => template ? cloneShipScene(template, pool.pieces, color, ghost) : null,
    [template, pool, color, ghost]);
  return scene ? <group scale={shipAssetScale(length)} userData={{ shipModel: "glb" }}>
    {/* Cached source geometry/neutral materials outlive each local node clone. */}
    <primitive object={scene} dispose={null} />
  </group> : <group userData={{ shipModel: "procedural", shipAssetFallback: true }}>{children}</group>;
}
