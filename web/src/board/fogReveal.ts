import { useEffect, useRef, useState } from "react";
import type { Tile } from "../components/BoardView.types";
import { isHiddenTile } from "./publicTiles";
import { useReducedMotion } from "../game/motion";

export const FOG_REVEAL_MS = 420;
export interface RevealFrame {
  key: string;
  tick: number;
  tiles: Tile[];
  connected: boolean;
}
export interface RevealBaseline extends RevealFrame {
  visible: boolean[];
  awaitingFresh: boolean;
}

/** Committed-frame presentation only. History/events never trigger a reveal. */
export function advanceFogReveal(previous: RevealBaseline | null, frame: RevealFrame): {
  baseline: RevealBaseline; revealed: number[];
} {
  const baseline = (awaitingFresh = !frame.connected): RevealBaseline =>
    ({ ...frame, visible: frame.tiles.map(t => !isHiddenTile(t)), awaitingFresh });
  if (!Number.isSafeInteger(frame.tick) || frame.tick < 0)
    return { baseline: previous ?? { ...baseline(true), tick: -1 }, revealed: [] };
  if (!previous || previous.key !== frame.key) return { baseline: baseline(), revealed: [] };
  if (!frame.connected) return { baseline: baseline(true), revealed: [] };
  if (frame.tick < previous.tick) return { baseline: previous, revealed: [] };
  if (previous.awaitingFresh) {
    // Reconnecting initially renders the cached frame. Baseline the first fresh
    // public tile array instead; discoveries committed while offline must not replay.
    return { baseline: frame.tiles === previous.tiles ? { ...previous, connected: true }
      : baseline(false), revealed: [] };
  }
  if (frame.tick <= previous.tick) return { baseline: previous, revealed: [] };
  const next = baseline(false);
  return { baseline: next, revealed: next.visible.flatMap((known, i) =>
    known && previous.visible[i] === false ? [i] : []) };
}

/** A single expiry timer, with no per-frame React updates or gameplay callbacks. */
export function useFogReveal(frame: RevealFrame, duration = FOG_REVEAL_MS): ReadonlyMap<number, number> {
  const previous = useRef<RevealBaseline | null>(null);
  const [reveals, setReveals] = useState<ReadonlyMap<number, number>>(() => new Map());
  const reduced = useReducedMotion();
  useEffect(() => {
    const changedMatch = previous.current?.key !== frame.key;
    const next = advanceFogReveal(previous.current, frame);
    previous.current = next.baseline;
    if (changedMatch || !frame.connected || reduced) setReveals(new Map());
    else if (next.revealed.length) {
      const now = performance.now();
      setReveals(old => new Map([...old, ...next.revealed.map(i => [i, now] as const)]));
    }
  }, [frame.key, frame.tick, frame.tiles, frame.connected, reduced]);
  useEffect(() => {
    if (!reveals.size) return;
    const deadline = Math.min(...reveals.values()) + duration;
    const timer = window.setTimeout(() => {
      const now = performance.now();
      setReveals(old => new Map([...old].filter(([, started]) => now - started < duration)));
    }, Math.max(1, deadline - performance.now()));
    return () => window.clearTimeout(timer);
  }, [reveals, duration]);
  return reveals;
}
