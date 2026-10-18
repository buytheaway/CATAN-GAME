import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Group, type Object3D } from "three";
import { useReducedMotion } from "../game/motion";
import { clonePieceScene, loadPieceAsset, pieceOffset, type PieceKind } from "./pieceAssets";
import { useVisualResources } from "./VisualResources";
import { piecePose, upgradeEchoPose, type PieceCue } from "./pieceFeedback";

export default function PieceVisual({ kind, color, ghost, cue, upgradeEcho = false, children }: {
  kind: PieceKind; color: string; ghost: boolean; cue?: PieceCue; upgradeEcho?: boolean; children: ReactNode;
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
  const animating = useRef(false);
  const visualData = useMemo(() => upgradeEcho ? { upgradeEcho: true, visualOnly: true } : { pieceVisual: kind }, [kind, upgradeEcho]);
  const reduced = useReducedMotion();
  const invalidate = useThree(s => s.invalidate);
  const update = () => {
    if (!visual.current) return false;
    const now = performance.now(), moving = !reduced && (!ghost || upgradeEcho);
    const pose = upgradeEcho && cue ? upgradeEchoPose(cue, now, moving) : piecePose(cue, now, moving);
    visual.current.position.y = pose.y;
    if (typeof pose.scale === "number") visual.current.scale.setScalar(pose.scale);
    else visual.current.scale.set(...pose.scale);
    visual.current.visible = !upgradeEcho || ("visible" in pose && pose.visible);
    visual.current.userData.appearing = pose.active;
    visual.current.userData.construction = pose.active ? cue?.kind : undefined;
    animating.current = pose.active;
    return pose.active;
  };
  useLayoutEffect(() => { update(); invalidate(); }, [cue, ghost, reduced, kind, upgradeEcho, invalidate]);
  useFrame(() => { if (animating.current && update()) invalidate(); });
  return <group position={pieceOffset(kind)}
    userData={{ pieceAsset: scene ? kind : undefined, pieceFallback: scene ? undefined : kind }}>
    <group ref={visual} userData={visualData}>
      {/* GLB nodes are local; geometry and neutral materials belong to the page cache. */}
      {scene ? <primitive object={scene} dispose={null} />
        // The original bevel extends below zero; normalize only fallback contact.
        : <group position={[0, kind === "road" ? .027 : .008, 0]}>{children}</group>}
    </group>
  </group>;
}
