import type { EdgeTuple } from "../components/BoardView.types";
import { SHIP_BUILD_MS, SHIP_MOVE_MS, type ShipCue } from "../board/shipFeedback";

export const SHIP_DEPART_MS = 350;
const clamp = (value: number) => Math.max(0, Math.min(1, value));
const ease = (t: number) => 1 - (1 - clamp(t)) ** 3;

/** Local visual transforms only. The authoritative edge anchor never moves. */
export function shipPose(edge: EdgeTuple, seconds: number, cue?: ShipCue, now = Infinity, moving = true) {
  const phase = edge[0] * .73 + edge[1] * .37;
  const elapsed = cue ? Math.max(0, now - cue.started) : Infinity;
  const duration = cue?.kind === "move" ? SHIP_MOVE_MS : SHIP_BUILD_MS;
  const active = moving && elapsed < duration;
  const t = !active ? 1 : cue?.kind === "move" ? ease((elapsed - 150) / (SHIP_MOVE_MS - 150)) : ease(elapsed / SHIP_BUILD_MS);
  return { y: (moving ? Math.sin(seconds * .9 + phase) * .008 : 0) - (active ? .15 * (1 - t) : 0),
    pitch: moving ? Math.cos(seconds * .65 + phase) * .009 : 0,
    roll: moving ? Math.sin(seconds * .75 + phase) * .018 : 0,
    scale: [active ? .9 + .1 * t : 1, active ? .4 + .6 * t : 1, active ? .9 + .1 * t : 1] as [number, number, number],
    active, kind: active ? cue!.kind : undefined };
}

export function shipDeparture(started: number, now: number) {
  const t = clamp((now - started) / SHIP_DEPART_MS);
  return { visible: t < 1, y: -.14 * ease(t), scale: 1 - .95 * ease(t) };
}
