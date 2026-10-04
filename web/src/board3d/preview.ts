import type { BoardInteraction } from "../board/interaction";
import { edgeId } from "../board/constants";
import { edgePlacement, TILE_TOP, toScenePosition } from "./coordinates";
import type { BoardSnapshot, RenderBuilding, RenderEdge } from "./types";

export type BuildPreview =
  | { kind: "settlement" | "city"; building: RenderBuilding }
  | { kind: "road" | "ship"; edge: RenderEdge };

/** Renderer-only projection of a hovered server target. No rule/affordability calculation. */
export function buildPreview(state: BoardSnapshot, interaction: Pick<BoardInteraction,
  "action" | "targets" | "selection" | "legal">, hover: string | null): BuildPreview | null {
  const owner = interaction.legal?.pid;
  if (!hover || owner == null || interaction.selection.waiting || interaction.selection.victim) return null;
  const { action, targets } = interaction;
  if (action === "settlement" || action === "city") {
    const vid = targets.vertices.find(id => hover === `v:${id}`);
    const point = vid == null ? null : state.vertices[vid];
    return point && vid != null ? { kind: action, building: {
      vertexId: vid, owner, level: action === "city" ? 2 : 1,
      position: toScenePosition(point, state.size, TILE_TOP + 0.035),
    } } : null;
  }
  if (action === "road" || action === "ship") {
    const edge = targets.edges.find(e => hover === `e:${edgeId(e)}`);
    const a = edge && state.vertices[edge[0]], b = edge && state.vertices[edge[1]];
    return edge && a && b ? { kind: action, edge: {
      edge, owner, ...edgePlacement(toScenePosition(a, state.size), toScenePosition(b, state.size)),
    } } : null;
  }
  return null;
}
