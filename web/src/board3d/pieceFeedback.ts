import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { OccupiedEdge, OccupiedVertex } from "../components/BoardView.types";
import { useReducedMotion } from "../game/motion";
import type { Point3D } from "./types";

export const ROAD_BUILD_MS = 450;
export const SETTLEMENT_BUILD_MS = 550;
export const CITY_UPGRADE_MS = 700;
export const CITY_ECHO_MS = 300;
export type ConstructionKind = "road" | "settlement" | "upgrade";
export type PieceCue = { kind: ConstructionKind; owner: number; started: number };
export type PieceFrame = { key: string; tick: number; connected: boolean; roads: OccupiedEdge; vertices: OccupiedVertex };
export type PieceBaseline = PieceFrame & { pieces: Map<string, string>; awaitingFresh: boolean };
export type PieceChange = { id: string; kind: ConstructionKind; owner: number };
const validOwner = (owner: unknown): owner is number => Number.isSafeInteger(owner) && (owner as number) >= 0;

function publicPieces(frame: Pick<PieceFrame, "roads" | "vertices">) {
  const pieces = new Map<string, string>();
  for (const [id, owner] of Object.entries(frame.roads)) {
    const ids = id.split(",").map(Number);
    if (/^\d+,\d+$/.test(id) && ids.every(Number.isSafeInteger) && ids[0] < ids[1] && validOwner(owner))
      pieces.set(`e:${id}`, `${owner}`);
  }
  for (const [id, value] of Object.entries(frame.vertices)) {
    if (/^\d+$/.test(id) && Number.isSafeInteger(Number(id)) && value?.length === 2
      && validOwner(value[0]) && (value[1] === 1 || value[1] === 2)) pieces.set(`v:${id}`, `${value[0]}:${value[1]}`);
  }
  return pieces;
}

/** Committed public occupancy only; no commands, events, terrain or private inventories. */
export function advancePieceFeedback(previous: PieceBaseline | null, frame: PieceFrame): { baseline: PieceBaseline; changes: PieceChange[] } {
  const baseline = (awaitingFresh = !frame.connected): PieceBaseline => ({ key: frame.key, tick: frame.tick,
    connected: frame.connected, roads: frame.roads, vertices: frame.vertices, pieces: publicPieces(frame), awaitingFresh });
  const quiet = (next: PieceBaseline) => ({ baseline: next, changes: [] });
  if (!Number.isSafeInteger(frame.tick) || frame.tick < 0) return quiet(previous ?? { ...baseline(true), tick: -1 });
  if (!previous || previous.key !== frame.key || !frame.connected) return quiet(baseline());
  if (frame.tick < previous.tick) return quiet(previous);
  if (previous.awaitingFresh) return quiet(frame.roads === previous.roads && frame.vertices === previous.vertices
    ? { ...previous, connected: true } : baseline(false));
  if (frame.tick <= previous.tick) return quiet(previous);
  const next = baseline(false);
  if (frame.tick !== previous.tick + 1) return quiet(next);
  // Removals, owner replacement and downgrades cannot identify a construction.
  if ([...previous.pieces].some(([id, signature]) => !next.pieces.has(id)
    || next.pieces.get(id) !== signature && !(id.startsWith("v:") && signature.endsWith(":1")
      && next.pieces.get(id) === `${signature.slice(0, -1)}2`))) return quiet(next);
  const changes: PieceChange[] = [];
  for (const [id, signature] of next.pieces) {
    const before = previous.pieces.get(id);
    if (signature === before) continue;
    const owner = Number(signature.split(":")[0]);
    if (id.startsWith("e:")) changes.push({ id, owner, kind: "road" });
    else if (before) changes.push({ id, owner, kind: "upgrade" });
    else if (signature.endsWith(":1")) changes.push({ id, owner, kind: "settlement" });
    else return quiet(next); // A newly hydrated city is not an observed upgrade.
  }
  return { baseline: next, changes };
}

export const pieceDuration = (kind: ConstructionKind) => kind === "road" ? ROAD_BUILD_MS
  : kind === "upgrade" ? CITY_UPGRADE_MS : SETTLEMENT_BUILD_MS;
const clamp = (t: number) => Math.max(0, Math.min(1, t));
const ease = (t: number) => 1 - (1 - clamp(t)) ** 3;

/** Only local visual height/scale change; edge and vertex anchors stay authoritative. */
export function piecePose(cue?: PieceCue, now = Infinity, moving = true): { y: number; scale: Point3D; active: boolean; kind?: ConstructionKind } {
  const elapsed = cue ? Math.max(0, now - cue.started) : Infinity;
  const active = moving && !!cue && elapsed < pieceDuration(cue.kind);
  if (!active) return { y: 0, scale: [1, 1, 1], active: false, kind: undefined };
  const t = cue.kind === "upgrade" ? ease((elapsed - 120) / (CITY_UPGRADE_MS - 120)) : ease(elapsed / pieceDuration(cue.kind));
  if (cue.kind === "road") return { y: 0, scale: [.12 + .88 * t, .7 + .3 * t, 1], active, kind: cue.kind };
  if (cue.kind === "settlement") return { y: -.12 * (1 - t), scale: [.9 + .1 * t, .32 + .68 * t, .9 + .1 * t], active, kind: cue.kind };
  return { y: -.025 * (1 - t), scale: [.9 + .1 * t, .45 + .55 * t, .9 + .1 * t], active, kind: cue.kind };
}

export function upgradeEchoPose(cue: PieceCue, now: number, moving = true) {
  const elapsed = Math.max(0, now - cue.started), t = ease(elapsed / CITY_ECHO_MS);
  const active = moving && cue.kind === "upgrade" && elapsed < CITY_ECHO_MS;
  return { y: -.055 * t, scale: 1 - .9 * t, visible: active, active };
}

const useCommittedEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;
/** Kept above the renderer toggle: static views still consume every public baseline. */
export function usePieceFeedback(frame: PieceFrame, enabled: boolean): ReadonlyMap<string, PieceCue> {
  const previous = useRef<PieceBaseline | null>(null), reduced = useReducedMotion();
  const [feedback, setFeedback] = useState<{ key: string; cues: Map<string, PieceCue> }>({ key: frame.key, cues: new Map() });
  useCommittedEffect(() => {
    const before = previous.current, next = advancePieceFeedback(before, frame); previous.current = next.baseline;
    if (!enabled || reduced || !frame.connected || before?.key !== frame.key || next.baseline.awaitingFresh) {
      setFeedback(old => old.cues.size || old.key !== frame.key ? { key: frame.key, cues: new Map() } : old); return;
    }
    if (next.baseline === before) return;
    const now = performance.now();
    setFeedback(old => {
      const cues = new Map([...old.cues].filter(([id, cue]) => next.baseline.pieces.get(id)
        === (cue.kind === "road" ? `${cue.owner}` : `${cue.owner}:${cue.kind === "upgrade" ? 2 : 1}`)));
      for (const { id, ...change } of next.changes) cues.set(id, { ...change, started: now });
      return !next.changes.length && cues.size === old.cues.size ? old : { key: frame.key, cues };
    });
  }, [frame.key, frame.tick, frame.roads, frame.vertices, frame.connected, enabled, reduced]);
  useEffect(() => {
    if (!feedback.cues.size) return;
    const deadline = Math.min(...[...feedback.cues.values()].map(cue => cue.started + pieceDuration(cue.kind)));
    const timer = window.setTimeout(() => {
      const now = performance.now();
      setFeedback(old => ({ ...old, cues: new Map([...old.cues].filter(([, cue]) => now < cue.started + pieceDuration(cue.kind))) }));
    }, Math.max(1, deadline - performance.now()));
    return () => window.clearTimeout(timer);
  }, [feedback]);
  return enabled && !reduced && frame.connected && feedback.key === frame.key ? feedback.cues : new Map();
}
