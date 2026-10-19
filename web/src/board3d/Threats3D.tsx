import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import type { Group, Mesh } from "three";
import { threatCueKey, type ThreatCue } from "../board/threatFeedback";
import { Pirate3D, PirateBody3D, Robber3D, RobberBody3D } from "./Pieces3D";
import { useAmbientMotion } from "./SceneMotion";
import { threatAnchor, threatDeparture, threatPose, theftPose } from "./threatMotion";
import { useVisualResources } from "./VisualResources";
import { VISUAL } from "./materials";
import type { BoardRenderModel, Point3D } from "./types";

const ignoreRaycast = () => undefined;
/** Receives only public render figures/centers and closed finite cues; no hands or rules. */
export default function Threats3D({ robbers, pirate, positions, cues, moving }: {
  robbers: BoardRenderModel["robbers"]; pirate: BoardRenderModel["pirate"];
  positions: ReadonlyMap<number, Point3D>; cues: ReadonlyMap<string, ThreatCue>; moving: boolean;
}) {
  const figures = useMemo(() => [...robbers.map((figure, index) => ({ ...figure, kind: "robber" as const, slot: `robber:${index}` })),
    ...(pirate ? [{ ...pirate, kind: "pirate" as const, slot: "pirate" }] : [])], [robbers, pirate]);
  const nodes = useRef(new Map<string, Group>()), echoes = useRef(new Map<string, Group>()), cards = useRef(new Map<string, Mesh>());
  const finite = useRef(false), pool = useVisualResources(), invalidate = useThree(s => s.invalidate);
  const effects = useMemo(() => [...cues].flatMap(([id, cue]) => {
    const from = positions.get(cue.from), to = positions.get(cue.to);
    return moving && to && (cue.path === "snap" || from) && figures.some(figure => threatCueKey(figure.kind, figure.tileIndex) === id)
      ? [{ id, cue, from, to }] : [];
  }), [cues, figures, positions, moving]);
  const seconds = useAmbientMotion(() => update(), moving && !!pirate);
  function update() {
    const now = performance.now(); let active = false;
    for (const figure of figures) {
      const id = threatCueKey(figure.kind, figure.tileIndex), node = nodes.current.get(figure.slot); if (!node) continue;
      const cue = cues.get(id), from = cue ? positions.get(cue.from) : undefined;
      const pose = threatPose(figure.kind, from ?? figure.position, figure.position, from ? cue : undefined, now, seconds.current, moving);
      node.position.set(...pose.position); node.scale.setScalar(pose.scale); node.rotation.set(pose.pitch, 0, pose.roll);
      node.userData.moving = pose.moving; node.userData.arriving = pose.arriving; active ||= pose.active;
    }
    for (const { id, cue } of effects) {
      const echo = echoes.current.get(id);
      if (echo) {
        const pose = threatDeparture(cue.started, now, moving); echo.visible = pose.visible;
        echo.position.y = pose.y; echo.scale.setScalar(pose.scale); active ||= pose.visible;
      }
      const card = cards.current.get(id);
      if (card) {
        const pose = theftPose(cue.started, now, moving); card.visible = pose.visible;
        card.position.set(...pose.position); card.rotation.set(...pose.rotation); card.scale.set(.14 * pose.scale, .20 * pose.scale, .014 * pose.scale);
        active ||= pose.visible;
      }
    }
    finite.current = active; return active;
  }
  useLayoutEffect(() => { update(); invalidate(); }, [figures, cues, positions, moving, invalidate]);
  useFrame(() => { if (finite.current && update()) invalidate(); });
  return <group userData={{ threatFleet: true }}>
    {figures.map(figure => {
      const Component = figure.kind === "robber" ? Robber3D : Pirate3D;
      return <Component key={figure.slot} position={figure.position} tileIndex={figure.tileIndex}
        visualRef={node => { if (node) nodes.current.set(figure.slot, node); else nodes.current.delete(figure.slot); }} />;
    })}
    {effects.map(({ id, cue, from, to }) => <group key={`${id}:${cue.started}`}>
      {cue.path === "endpoints" && from && <group position={threatAnchor(cue.kind, from)} rotation={[0, cue.kind === "pirate" ? -.3 : 0, 0]}>
        <group ref={node => { if (node) echoes.current.set(id, node); else echoes.current.delete(id); }}
          userData={{ departureVisual: true, visualOnly: true }}>
          {cue.kind === "robber" ? <RobberBody3D ghost /> : <PirateBody3D ghost />}
        </group>
      </group>}
      {cue.theft && <group position={threatAnchor(cue.kind, to)}>
        <mesh ref={node => { if (node) cards.current.set(id, node); else cards.current.delete(id); }}
          geometry={pool.geometry("box")} material={pool.standard(VISUAL.ivory)} raycast={ignoreRaycast}
          userData={{ theftVisual: true, visualOnly: true }} />
      </group>}
    </group>)}
  </group>;
}
