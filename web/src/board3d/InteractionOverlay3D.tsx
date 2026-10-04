import { useMemo, useState } from "react";
import type { BoardInteraction } from "../board/interaction";
import { edgeId } from "../board/constants";
import { edgePlacement, toScenePosition, TILE_TOP } from "./coordinates";
import type { BoardSnapshot } from "./types";

export default function InteractionOverlay3D({ state, interaction }: {
  state: BoardSnapshot; interaction: BoardInteraction;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const { targets, selection } = interaction;
  const edges = useMemo(() => selection.shipSource && !targets.edges.some(e => edgeId(e) === edgeId(selection.shipSource!))
    ? [...targets.edges, selection.shipSource] : targets.edges, [targets.edges, selection.shipSource]);
  const color = (key: string, selected = false) => selected ? "#f59e0b" : hover === key ? "#56c6ff" : "#22c55e";
  return <group>
    {targets.vertices.map(vid => {
      const point = state.vertices[vid];
      if (!point) return null;
      const key = `v:${vid}`;
      const position = toScenePosition(point, state.size, state.occupied_v[vid] ? TILE_TOP + 0.65 : TILE_TOP + 0.09);
      return <group key={key} position={position} userData={{ targetType: "vertex", vertexId: vid }}
        onPointerOver={e => { e.stopPropagation(); setHover(key); }} onPointerOut={() => setHover(null)}
        onClick={e => { e.stopPropagation(); if (e.delta < 5) interaction.onVertexClick(vid); }}>
        <mesh rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.15, hover === key ? 0.28 : 0.24, 24]} />
          <meshBasicMaterial color={color(key)} transparent opacity={0.9} depthWrite={false} />
        </mesh>
        <mesh rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.25, 16]} />
          <meshBasicMaterial color={color(key)} transparent opacity={0.12} depthWrite={false} />
        </mesh>
      </group>;
    })}
    {edges.map(edge => {
      const a = state.vertices[edge[0]], b = state.vertices[edge[1]];
      if (!a || !b) return null;
      const key = `e:${edgeId(edge)}`;
      const placement = edgePlacement(toScenePosition(a, state.size), toScenePosition(b, state.size));
      const source = targets.sources.some(e => edgeId(e) === edgeId(edge));
      const selected = !!selection.shipSource && edgeId(edge) === edgeId(selection.shipSource);
      const position = [...placement.position] as [number, number, number];
      position[1] = source || selected ? TILE_TOP + 0.48 : TILE_TOP + 0.1;
      return <mesh key={key} position={position} rotation={[0, placement.rotation, 0]}
        userData={{ targetType: "edge", edge, source, selected }}
        onPointerOver={e => { e.stopPropagation(); setHover(key); }} onPointerOut={() => setHover(null)}
        onClick={e => { e.stopPropagation(); if (e.delta < 5) interaction.onEdgeClick(edge); }}>
        <boxGeometry args={[placement.length * 0.85, 0.07, hover === key ? 0.24 : 0.18]} />
        <meshBasicMaterial color={color(key, selected)} transparent opacity={hover === key || selected ? 0.85 : 0.55} depthWrite={false} />
      </mesh>;
    })}
  </group>;
}
