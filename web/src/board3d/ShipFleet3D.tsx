import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import type { Group } from "three";
import type { EdgeTuple, VertexCoordinates } from "../components/BoardView.types";
import type { ShipCue } from "../board/shipFeedback";
import { edgeId } from "../board/constants";
import { edgePlacement, toScenePosition } from "./coordinates";
import { Ship3D, ShipBody3D } from "./Pieces3D";
import { useAmbientMotion } from "./SceneMotion";
import { shipDeparture, shipPose } from "./shipMotion";
import type { RenderEdge } from "./types";
import type { ShipModel } from "./shipAssets";

/** No terrain, hidden recipes, legal rules or command callbacks are accepted here. */
export default function ShipFleet3D({ ships, cues, vertices, edges, size, colors, moving, model }: {
  ships: RenderEdge[]; cues: ReadonlyMap<string, ShipCue>; vertices: VertexCoordinates; edges: EdgeTuple[]; size: number;
  colors: ReadonlyMap<number, string>; moving: boolean; model?: ShipModel;
}) {
  const nodes = useRef(new Map<string, Group>()), echoes = useRef(new Map<string, Group>());
  const invalidate = useThree(s => s.invalidate);
  const departures = useMemo(() => [...cues].flatMap(([id, cue]) => {
    if (cue.kind !== "move" || !cue.from || !moving || ships.some(s => edgeId(s.edge) === edgeId(cue.from!))
      || !ships.some(s => edgeId(s.edge) === id && s.owner === cue.owner)) return [];
    const original = edges.find(e => edgeId(e) === edgeId(cue.from!)) ?? cue.from;
    const a = vertices[original[0]], b = vertices[original[1]];
    return a && b ? [{ id, cue, placement: edgePlacement(toScenePosition(a, size), toScenePosition(b, size)) }] : [];
  }), [cues, ships, vertices, edges, size, moving]);
  const seconds = useAmbientMotion(() => update(), moving && ships.length > 0);
  function update() {
    const now = performance.now(); let active = false;
    for (const ship of ships) {
      const id = edgeId(ship.edge), node = nodes.current.get(id);
      if (!node) continue;
      const cue = cues.get(id), pose = shipPose(ship.edge, seconds.current, cue?.owner === ship.owner ? cue : undefined, now, moving);
      node.position.y = pose.y; node.rotation.set(pose.pitch, 0, pose.roll); node.scale.set(...pose.scale);
      node.userData.appearing = pose.active; node.userData.shipEffect = pose.kind; active ||= pose.active;
    }
    for (const { id, cue } of departures) {
      const node = echoes.current.get(id); if (!node) continue;
      const pose = shipDeparture(cue.started, now); node.visible = moving && pose.visible;
      node.position.y = pose.y; node.scale.setScalar(pose.scale);
    }
    return active;
  }
  useLayoutEffect(() => { update(); invalidate(); }, [ships, cues, moving, invalidate]);
  useFrame(() => { if (update()) invalidate(); });
  return <group userData={{ shipFleet: true }}>
    {ships.map(ship => <Ship3D key={edgeId(ship.edge)} ship={ship} color={colors.get(ship.owner)} model={model}
      visualRef={node => { if (node) nodes.current.set(edgeId(ship.edge), node); else nodes.current.delete(edgeId(ship.edge)); }} />)}
    {departures.map(({ id, cue, placement }) => <group key={`${id}:${cue.started}`} position={placement.position} rotation={[0, placement.rotation, 0]}>
      <group ref={node => { if (node) echoes.current.set(id, node); else echoes.current.delete(id); }}
        userData={{ shipDeparture: true, fromEdge: cue.from, visualOnly: true }}>
        <ShipBody3D length={placement.length} color={colors.get(cue.owner) ?? "#ffffff"} ghost model={model} />
      </group>
    </group>)}
  </group>;
}
