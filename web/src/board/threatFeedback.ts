import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Tile } from "../components/BoardView.types";
import { useReducedMotion } from "../game/motion";
import { publicTileVisual } from "./publicTiles";

export const THREAT_MOVE_MS = 650;
export const THREAT_ENDPOINT_MS = 850;
export const THREAT_DEPART_MS = 300;
export const THEFT_MS = 700;
export type ThreatKind = "robber" | "pirate";
export type ThreatEvent = { id: number; tick: number; type: string; actor_pid: number;
  from_tile?: number | null; tile?: number; victim_pid?: number; quantity?: number };
export type ThreatFrame = { key: string; tick: number; connected: boolean; tiles: Tile[];
  edgeAdjacency: Record<string, number[]>; robbers: readonly number[]; pirate: number | null; events: readonly ThreatEvent[] };
export type ThreatCue = { kind: ThreatKind; from: number; to: number; path: "adjacent" | "endpoints" | "snap";
  eventId: number; theft: boolean; started: number };
export type ThreatBaseline = ThreatFrame & { positions: Set<number>; validFigures: boolean;
  known: Map<number, "land" | "sea">; lastEvent: number; awaitingFresh: boolean };

/** Closed public copy, including for entitled recipients. Private fields are never read. */
export function selectThreatEvents(source: readonly ThreatEvent[]): ThreatEvent[] {
  return source.flatMap((event): ThreatEvent[] => event.type === "move_robber" || event.type === "move_pirate"
    ? [{ id: event.id, tick: event.tick, type: event.type, actor_pid: event.actor_pid, from_tile: event.from_tile, tile: event.tile }]
    : event.type === "theft" ? [{ id: event.id, tick: event.tick, type: event.type, actor_pid: event.actor_pid,
      victim_pid: event.victim_pid, quantity: event.quantity }] : []);
}
const validId = (id: unknown): id is number => Number.isSafeInteger(id) && (id as number) >= 0;
const validTile = (id: unknown, tiles: Tile[]): id is number => validId(id) && id < tiles.length;
export const threatCueKey = (kind: ThreatKind, tile: number) => `${kind}:${tile}`;
export const threatDuration = (cue: Pick<ThreatCue, "path" | "theft">) => Math.max(
  cue.path === "snap" ? 0 : cue.path === "adjacent" ? THREAT_MOVE_MS : THREAT_ENDPOINT_MS, cue.theft ? THEFT_MS : 0);

function publicKnown(tiles: Tile[]) {
  return new Map(tiles.flatMap((tile, id): [number, "land" | "sea"][] => {
    if (!tile || tile.visibility !== undefined && tile.visibility !== "revealed") return [];
    // The number/token and any hidden tile contents do not participate in motion.
    const visual = publicTileVisual({ visibility: tile.visibility, terrain: tile.terrain });
    return visual.visibility === "revealed" ? [[id, visual.terrain === "sea" ? "sea" : "land"]] : [];
  }));
}

/** Adjacent committed facts only. Hidden/offboard/ambiguous transitions snap safely. */
export function advanceThreatFeedback(previous: ThreatBaseline | null, frame: ThreatFrame): {
  baseline: ThreatBaseline; changes: Omit<ThreatCue, "started">[];
} {
  const baseline = (awaitingFresh = !frame.connected): ThreatBaseline => {
    const positions = new Set(frame.robbers);
    return { key: frame.key, tick: frame.tick, connected: frame.connected, tiles: frame.tiles,
      edgeAdjacency: frame.edgeAdjacency, robbers: frame.robbers, pirate: frame.pirate, events: frame.events,
      positions, validFigures: positions.size === frame.robbers.length && frame.robbers.every(id => id === -1 || validTile(id, frame.tiles))
        && (frame.pirate === null || validTile(frame.pirate, frame.tiles)), known: publicKnown(frame.tiles),
      lastEvent: Math.max(0, ...frame.events.map(event => validId(event.id) ? event.id : 0)), awaitingFresh };
  };
  const quiet = (next: ThreatBaseline) => ({ baseline: next, changes: [] });
  if (!Number.isSafeInteger(frame.tick) || frame.tick < 0) return quiet(previous ?? { ...baseline(true), tick: -1 });
  if (!previous || previous.key !== frame.key || !frame.connected) return quiet(baseline());
  if (frame.tick < previous.tick) return quiet(previous);
  if (previous.awaitingFresh) return quiet(frame.tiles === previous.tiles ? { ...previous, connected: true } : baseline(false));
  if (frame.tick <= previous.tick) return quiet(previous);
  const next = baseline(false);
  if (frame.tick !== previous.tick + 1 || !previous.validFigures || !next.validFigures) return quiet(next);
  const removed = [...previous.positions].filter(id => !next.positions.has(id));
  const added = [...next.positions].filter(id => !previous.positions.has(id));
  const pirateChanged = frame.pirate !== previous.pirate;
  if (!removed.length && !added.length && !pirateChanged) return quiet(next);
  // One command can move one figure; never pair multiple changes by guessed identity.
  if (pirateChanged && (removed.length || added.length) || !pirateChanged && (removed.length !== 1 || added.length !== 1)) return quiet(next);
  const kind: ThreatKind = pirateChanged ? "pirate" : "robber";
  const from = pirateChanged ? previous.pirate : removed[0], to = pirateChanged ? frame.pirate : added[0];
  if (from === null || !validTile(to, frame.tiles) || from === to) return quiet(next);
  const offboardRobber = kind === "robber" && from === -1;
  if (!offboardRobber && !validTile(from, frame.tiles)) return quiet(next);
  const terrain = kind === "pirate" ? "sea" : "land";
  if ((offboardRobber ? [to] : [from, to]).some(id => previous.known.get(id) !== terrain || next.known.get(id) !== terrain)) return quiet(next);
  const fresh = frame.events.filter(event => event.tick === frame.tick && validId(event.id) && event.id > previous.lastEvent);
  const moves = fresh.filter(event => event.type === "move_robber" || event.type === "move_pirate");
  if (moves.length !== 1) return quiet(next);
  const event = moves[0];
  if (event.type !== `move_${kind}` || event.from_tile !== from || event.tile !== to || !validId(event.actor_pid)) return quiet(next);
  const thefts = fresh.filter(item => item.type === "theft");
  const theft = thefts.length === 1 && thefts[0].id > event.id && thefts[0].actor_pid === event.actor_pid
    && validId(thefts[0].victim_pid) && thefts[0].victim_pid !== event.actor_pid && thefts[0].quantity === 1;
  // An inactive canonical robber has no origin geometry. Only its public theft gets a card.
  if (offboardRobber) return theft ? { baseline: next, changes: [{ kind, from, to, path: "snap", eventId: event.id, theft }] } : quiet(next);
  const adjacent = Object.values(frame.edgeAdjacency).some(pair => Array.isArray(pair) && pair.length === 2 && pair.includes(from) && pair.includes(to));
  return { baseline: next, changes: [{ kind, from, to, path: adjacent ? "adjacent" : "endpoints", eventId: event.id, theft }] };
}

const useCommittedEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;
/** One finite expiry timer; quiet views still consume every public baseline. */
export function useThreatFeedback(frame: ThreatFrame, enabled: boolean): ReadonlyMap<string, ThreatCue> {
  const previous = useRef<ThreatBaseline | null>(null), reduced = useReducedMotion();
  const [feedback, setFeedback] = useState<{ key: string; cues: Map<string, ThreatCue> }>({ key: frame.key, cues: new Map() });
  useCommittedEffect(() => {
    const before = previous.current, next = advanceThreatFeedback(before, frame); previous.current = next.baseline;
    if (!enabled || reduced || !frame.connected || before?.key !== frame.key || next.baseline.awaitingFresh || !next.baseline.validFigures) {
      setFeedback(old => old.cues.size || old.key !== frame.key ? { key: frame.key, cues: new Map() } : old); return;
    }
    if (next.baseline === before) return;
    const now = performance.now();
    setFeedback(old => {
      const cues = new Map([...old.cues].filter(([, cue]) => cue.kind === "pirate" ? frame.pirate === cue.to : next.baseline.positions.has(cue.to)));
      for (const change of next.changes) cues.set(threatCueKey(change.kind, change.to), { ...change, started: now });
      return !next.changes.length && cues.size === old.cues.size ? old : { key: frame.key, cues };
    });
  }, [frame.key, frame.tick, frame.tiles, frame.edgeAdjacency, frame.robbers, frame.pirate, frame.events, frame.connected, enabled, reduced]);
  useEffect(() => {
    if (!feedback.cues.size) return;
    const deadline = Math.min(...[...feedback.cues.values()].map(cue => cue.started + threatDuration(cue)));
    const timer = window.setTimeout(() => {
      const now = performance.now();
      setFeedback(old => ({ ...old, cues: new Map([...old.cues].filter(([, cue]) => now < cue.started + threatDuration(cue))) }));
    }, Math.max(1, deadline - performance.now()));
    return () => window.clearTimeout(timer);
  }, [feedback]);
  return enabled && !reduced && frame.connected && feedback.key === frame.key ? feedback.cues : new Map();
}
