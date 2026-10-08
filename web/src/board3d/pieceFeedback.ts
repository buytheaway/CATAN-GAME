import { useEffect, useRef, useState } from "react";
import { edgeId } from "../board/constants";
import type { BoardRenderModel, Point3D } from "./types";
import type { PieceKind } from "./pieceAssets";

export const PIECE_APPEARANCE_MS = 260;
export function appearanceScale(kind: PieceKind, progress: number): Point3D {
  const t = Math.max(0, Math.min(1, progress)), ease = 1 - (1 - t) ** 3;
  return kind === "road" ? [1, .45 + .55 * ease, .92 + .08 * ease]
    : [.94 + .06 * ease, .82 + .18 * ease, .94 + .06 * ease];
}

export function pieceSignatures(model: Pick<BoardRenderModel, "roads" | "buildings">) {
  return new Map([
    ...model.roads.map(road => [`e:${edgeId(road.edge)}`, `${road.owner}`] as const),
    ...model.buildings.map(building => [`v:${building.vertexId}`, `${building.owner}:${building.level}`] as const),
  ]);
}

type PieceBaseline = { key: string; connected: boolean; pieces: Map<string, string> };
/** Null establishes a baseline. Only live committed occupancy changes produce feedback. */
export function confirmedPlacements(previous: PieceBaseline | null, current: Map<string, string>, matchKey: string, connected: boolean) {
  if (!previous || previous.key !== matchKey || !previous.connected || !connected) return null;
  return [...current.keys()].filter(key => current.get(key) !== previous.pieces.get(key));
}

export function usePieceFeedback(model: BoardRenderModel, matchKey: string, connected: boolean) {
  const previous = useRef<PieceBaseline | null>(null);
  const [feedback, setFeedback] = useState<{ key: string; tokens: Map<string, number> }>({ key: matchKey, tokens: new Map() });
  useEffect(() => {
    const current = pieceSignatures(model), before = previous.current;
    const changed = confirmedPlacements(before, current, matchKey, connected);
    previous.current = { key: matchKey, connected, pieces: current };
    // A restored board is a baseline, not a sequence of construction events.
    if (changed === null) {
      setFeedback(value => value.tokens.size || value.key !== matchKey ? { key: matchKey, tokens: new Map() } : value);
      return;
    }
    if (!changed.length) return;
    const token = performance.now();
    setFeedback(value => ({ key: matchKey, tokens: new Map([...current.keys()].flatMap(key =>
      changed.includes(key) ? [[key, token]] : value.tokens.has(key) ? [[key, value.tokens.get(key)!]] : [])) }));
  }, [model, matchKey, connected]);
  return feedback.key === matchKey && connected ? feedback.tokens : new Map<string, number>();
}
