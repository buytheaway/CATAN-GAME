import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { EdgeTuple, OccupiedEdge } from "../components/BoardView.types";
import { useReducedMotion } from "../game/motion";

export const SHIP_BUILD_MS = 550;
export const SHIP_MOVE_MS = 900;
export type ShipEvent = { id: number; tick: number; type: string; actor_pid: number };
export type ShipFrame = { key: string; tick: number; connected: boolean; ships: OccupiedEdge; events: readonly ShipEvent[] };
export type ShipCue = { kind: "build" | "move"; to: EdgeTuple; from?: EdgeTuple; owner: number; started: number };
type Change = Omit<ShipCue, "started">;
export type ShipBaseline = ShipFrame & { occupancy: Map<string, number>; lastEvent: number; awaitingFresh: boolean };

function publicShips(source: OccupiedEdge) {
  return new Map(Object.entries(source).filter(([key, pid]) => {
    const ids = key.split(",").map(Number);
    return /^\d+,\d+$/.test(key) && ids.length === 2 && ids.every(Number.isSafeInteger) && ids[0] < ids[1]
      && Number.isSafeInteger(pid) && pid! >= 0;
  }) as [string, number][]);
}
const edge = (id: string) => id.split(",").map(Number) as EdgeTuple;

/** Public occupancy facts only. No tiles, rules, resource inventory or predicted commands. */
export function advanceShipFeedback(previous: ShipBaseline | null, frame: ShipFrame): { baseline: ShipBaseline; changes: Change[] } {
  const baseline = (awaitingFresh = !frame.connected): ShipBaseline => ({ key: frame.key, tick: frame.tick,
    connected: frame.connected, ships: frame.ships, events: frame.events, awaitingFresh,
    occupancy: publicShips(frame.ships), lastEvent: Math.max(0, ...frame.events.map(e => Number.isSafeInteger(e.id) ? e.id : 0)) });
  const quiet = (next: ShipBaseline) => ({ baseline: next, changes: [] });
  if (!Number.isSafeInteger(frame.tick) || frame.tick < 0) return quiet(previous ?? { ...baseline(true), tick: -1 });
  if (!previous || previous.key !== frame.key || !frame.connected) return quiet(baseline());
  if (frame.tick < previous.tick) return quiet(previous);
  if (previous.awaitingFresh) return quiet(frame.ships === previous.ships
    ? { ...previous, connected: true } : baseline(false));
  if (frame.tick <= previous.tick) return quiet(previous);
  const next = baseline(false);
  // A coalesced gap may hide a move AND construction; never invent identity.
  if (frame.tick !== previous.tick + 1) return quiet(next);
  const added = [...next.occupancy].filter(([id, pid]) => previous.occupancy.get(id) !== pid);
  const removed = [...previous.occupancy].filter(([id, pid]) => next.occupancy.get(id) !== pid);
  if (!removed.length) return { baseline: next, changes: added.map(([id, owner]) => ({ kind: "build", to: edge(id), owner })) };
  const events = frame.events.filter(e => e.tick === frame.tick && Number.isSafeInteger(e.id) && e.id > previous.lastEvent
    && ["move_ship", "build_ship"].includes(e.type));
  if (added.length === 1 && removed.length === 1 && added[0][0] !== removed[0][0]
    && added[0][1] === removed[0][1] && events.length === 1 && events[0].type === "move_ship"
    && events[0].actor_pid === added[0][1]) return { baseline: next, changes: [{ kind: "move",
      from: edge(removed[0][0]), to: edge(added[0][0]), owner: added[0][1] }] };
  return quiet(next);
}

const useCommittedEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;
/** Above the 2D/3D toggle, with one finite expiry timer and reconnect freshness fence. */
export function useShipFeedback(frame: ShipFrame, enabled: boolean): ReadonlyMap<string, ShipCue> {
  const previous = useRef<ShipBaseline | null>(null), reduced = useReducedMotion();
  const [feedback, setFeedback] = useState<{ key: string; cues: Map<string, ShipCue> }>({ key: frame.key, cues: new Map() });
  useCommittedEffect(() => {
    const before = previous.current, next = advanceShipFeedback(before, frame); previous.current = next.baseline;
    if (!enabled || reduced || !frame.connected || before?.key !== frame.key || next.baseline.awaitingFresh) {
      setFeedback(old => old.cues.size || old.key !== frame.key ? { key: frame.key, cues: new Map() } : old); return;
    }
    if (next.baseline === before) return;
    const now = performance.now();
    setFeedback(old => {
      const cues = new Map([...old.cues].filter(([id, cue]) => next.baseline.occupancy.get(id) === cue.owner));
      for (const change of next.changes) cues.set(change.to.join(","), { ...change, started: now });
      return !next.changes.length && cues.size === old.cues.size ? old : { key: frame.key, cues };
    });
  }, [frame.key, frame.tick, frame.ships, frame.events, frame.connected, enabled, reduced]);
  useEffect(() => {
    if (!feedback.cues.size) return;
    const deadline = Math.min(...[...feedback.cues.values()].map(c => c.started + (c.kind === "move" ? SHIP_MOVE_MS : SHIP_BUILD_MS)));
    const timer = window.setTimeout(() => {
      const now = performance.now();
      setFeedback(old => ({ ...old, cues: new Map([...old.cues].filter(([, c]) =>
        now < c.started + (c.kind === "move" ? SHIP_MOVE_MS : SHIP_BUILD_MS))) }));
    }, Math.max(1, deadline - performance.now()));
    return () => window.clearTimeout(timer);
  }, [feedback]);
  return enabled && !reduced && frame.connected && feedback.key === frame.key ? feedback.cues : new Map();
}
