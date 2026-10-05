import { useEffect, useMemo, useState } from "react";
import { useThree } from "@react-three/fiber";
import type { BoardInteraction } from "../board/interaction";
import { edgeId } from "../board/constants";
import { edgePlacement, toScenePosition, TILE_TOP } from "./coordinates";
import { targetColor } from "./materials";
import { buildPreview } from "./preview";
import { City3D, Road3D, Settlement3D, Ship3D } from "./Pieces3D";
import { useVisualResources } from "./VisualResources";
import type { BoardSnapshot } from "./types";
import { colorForPlayer } from "../board/colors";

export default function InteractionOverlay3D({ state, interaction }: {
  state: BoardSnapshot; interaction: BoardInteraction;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const pool = useVisualResources();
  const gl = useThree(s => s.gl);
  const { targets, selection } = interaction;
  const edges = useMemo(() => selection.shipSource && !targets.edges.some(e => edgeId(e) === edgeId(selection.shipSource!))
    ? [...targets.edges, selection.shipSource] : targets.edges, [targets.edges, selection.shipSource]);
  const preview = buildPreview(state, interaction, hover);
  const activeHover = hover != null && (targets.vertices.some(v => hover === "v:" + v)
    || edges.some(e => hover === "e:" + edgeId(e)));
  useEffect(() => {
    gl.domElement.style.cursor = activeHover ? "pointer" : "";
    return () => { gl.domElement.style.cursor = ""; };
  }, [gl, activeHover]);
  return <group>
    {targets.vertices.map(vid => {
      const point = state.vertices[vid];
      if (!point) return null;
      const key = "v:" + vid;
      const hovered = hover === key;
      const position = toScenePosition(point, state.size, state.occupied_v[vid] ? TILE_TOP + 0.54 : TILE_TOP + 0.06);
      return <group key={key} position={position} userData={{ targetType: "vertex", vertexId: vid }}
        onPointerOver={e => { e.stopPropagation(); setHover(key); }} onPointerOut={() => setHover(null)}
        onClick={e => { e.stopPropagation(); if (e.delta < 5) interaction.onVertexClick(vid); }}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} geometry={pool.ring(0.12, hovered ? 0.23 : 0.17)}
          material={pool.flat(targetColor(hovered), hovered ? 0.85 : 0.35)} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} scale={[0.29, 0.29, 1]}
          geometry={pool.geometry("disc")} material={pool.flat(targetColor(hovered), 0)} />
      </group>;
    })}
    {edges.map(edge => {
      const a = state.vertices[edge[0]], b = state.vertices[edge[1]];
      if (!a || !b) return null;
      const key = "e:" + edgeId(edge);
      const placement = edgePlacement(toScenePosition(a, state.size), toScenePosition(b, state.size));
      const source = targets.sources.some(e => edgeId(e) === edgeId(edge));
      const selected = !!selection.shipSource && edgeId(edge) === edgeId(selection.shipSource);
      const hovered = hover === key;
      const position = [...placement.position] as [number, number, number];
      position[1] = source || selected ? TILE_TOP + 0.48 : TILE_TOP + 0.07;
      return <group key={key} position={position} rotation={[0, placement.rotation, 0]}
        userData={{ targetType: "edge", edge, source, selected }}
        onPointerOver={e => { e.stopPropagation(); setHover(key); }} onPointerOut={() => setHover(null)}
        onClick={e => { e.stopPropagation(); if (e.delta < 5) interaction.onEdgeClick(edge); }}>
        <mesh scale={[placement.length * 0.85, 0.055, 0.28]}
          geometry={pool.geometry("box")} material={pool.flat(targetColor(hovered, selected), 0)} />
        {[-1, 1].map(side => <mesh key={side} position={[0, 0.025, side * 0.12]}
          scale={[placement.length * 0.82, 0.025, selected ? 0.035 : hovered ? 0.025 : 0.015]}
          geometry={pool.geometry("box")} material={pool.flat(targetColor(hovered, selected), hovered || selected ? 1 : 0.38)} />)}
        {selected && [-1, 1].map(end => <mesh key={end} position={[end * placement.length * 0.41, 0.025, 0]}
          scale={[0.035, 0.025, 0.27]} geometry={pool.geometry("box")} material={pool.flat(targetColor(false, true))} />)}
      </group>;
    })}
    {preview?.kind === "settlement" && <Settlement3D building={preview.building} color={colorForPlayer(preview.building.owner, state.players)} ghost />}
    {preview?.kind === "city" && <City3D building={preview.building} color={colorForPlayer(preview.building.owner, state.players)} ghost />}
    {preview?.kind === "road" && <Road3D road={preview.edge} color={colorForPlayer(preview.edge.owner, state.players)} ghost />}
    {preview?.kind === "ship" && <Ship3D ship={preview.edge} color={colorForPlayer(preview.edge.owner, state.players)} ghost />}
  </group>;
}
