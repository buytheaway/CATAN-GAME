import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Group, type Object3D } from "three";
import { useReducedMotion } from "../game/motion";
import { clonePieceScene, loadPieceAsset, pieceOffset, type PieceKind } from "./pieceAssets";
import { useVisualResources } from "./VisualResources";
import { appearanceScale, PIECE_APPEARANCE_MS } from "./pieceFeedback";

export default function PieceVisual({ kind, color, ghost, appearance, children }: {
  kind: PieceKind; color: string; ghost: boolean; appearance?: number; children: ReactNode;
}) {
  const [loaded, setLoaded] = useState<{ kind: PieceKind; template: Object3D | null } | null>(null);
  useEffect(() => {
    let active = true;
    loadPieceAsset(kind).then(template => { if (active) setLoaded({ kind, template }); });
    return () => { active = false; };
  }, [kind]);
  const template = loaded?.kind === kind ? loaded.template : null;
  const pool = useVisualResources();
  const scene = useMemo(() => template ? clonePieceScene(template, pool.pieces, color, ghost) : null,
    [template, pool, color, ghost]);
  const visual = useRef<Group>(null);
  const started = useRef<number | null>(null);
  const reduced = useReducedMotion();
  const invalidate = useThree(s => s.invalidate);
  useEffect(() => {
    const elapsed = appearance == null ? Infinity : performance.now() - appearance;
    started.current = elapsed < PIECE_APPEARANCE_MS && !ghost && !reduced ? appearance! : null;
    if (visual.current) {
      visual.current.scale.set(...appearanceScale(kind, started.current == null ? 1 : elapsed / PIECE_APPEARANCE_MS));
      visual.current.userData.appearing = started.current != null;
    }
    invalidate();
    return () => { started.current = null; };
  }, [appearance, ghost, reduced, kind, invalidate]);
  useFrame(() => {
    if (started.current == null || !visual.current) return;
    const t = Math.min(1, (performance.now() - started.current) / PIECE_APPEARANCE_MS);
    visual.current.scale.set(...appearanceScale(kind, t));
    if (t < 1) invalidate();
    else { started.current = null; visual.current.userData.appearing = false; }
  });
  return <group position={pieceOffset(kind)}
    userData={{ pieceAsset: scene ? kind : undefined, pieceFallback: scene ? undefined : kind }}>
    <group ref={visual}>
      {/* GLB nodes are local; geometry and neutral materials belong to the page cache. */}
      {scene ? <primitive object={scene} dispose={null} />
        // The original bevel extends below zero; normalize only fallback contact.
        : <group position={[0, kind === "road" ? .027 : .008, 0]}>{children}</group>}
    </group>
  </group>;
}
