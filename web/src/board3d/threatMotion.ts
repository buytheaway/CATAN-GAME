import { THREAT_DEPART_MS, THREAT_ENDPOINT_MS, THREAT_MOVE_MS, THEFT_MS, type ThreatCue, type ThreatKind } from "../board/threatFeedback";
import { TILE_TOP } from "./coordinates";
import type { Point3D } from "./types";

const clamp = (t: number) => Math.max(0, Math.min(1, t));
const ease = (t: number) => { const x = clamp(t); return x * x * (3 - 2 * x); };
export const threatAnchor = (kind: ThreatKind, position: Point3D): Point3D => kind === "robber"
  ? [position[0] + .48, TILE_TOP, position[2] + .1] : [position[0] + .15, TILE_TOP + .03, position[2] + .24];

/** Relative to the exact final anchor; only a known adjacent pair may interpolate. */
export function threatPose(kind: ThreatKind, from: Point3D, to: Point3D, cue?: ThreatCue, now = Infinity, seconds = 0, moving = true) {
  const elapsed = cue ? Math.max(0, now - cue.started) : Infinity;
  const duration = cue?.path === "adjacent" ? THREAT_MOVE_MS : THREAT_ENDPOINT_MS;
  const active = moving && !!cue && cue.path !== "snap" && elapsed < duration;
  const t = active ? ease(cue.path === "adjacent" ? elapsed / duration : (elapsed - 120) / (duration - 120)) : 1;
  const travel = active && cue?.path === "adjacent";
  const ambient = kind === "pirate" && moving;
  const dx = travel ? (from[0] - to[0]) * (1 - t) : 0, dz = travel ? (from[2] - to[2]) * (1 - t) : 0;
  const yaw = kind === "pirate" ? -.3 : 0;
  return { position: [dx * Math.cos(yaw) - dz * Math.sin(yaw),
    (travel ? Math.sin(t * Math.PI) * .22 : active ? -.1 * (1 - t) : 0) + (ambient ? Math.sin(seconds * .9) * .004 : 0),
    dx * Math.sin(yaw) + dz * Math.cos(yaw)] as Point3D,
    scale: active && cue?.path === "endpoints" ? .6 + .4 * t : 1,
    pitch: ambient ? Math.cos(seconds * .65) * .006 : 0, roll: ambient ? Math.sin(seconds * .75) * .012 : 0,
    moving: travel, arriving: active && (!travel || t > .72), active };
}

export function threatDeparture(started: number, now: number, moving = true) {
  const t = ease((now - started) / THREAT_DEPART_MS);
  return { y: -.08 * t, scale: 1 - .9 * t, visible: moving && now - started < THREAT_DEPART_MS };
}

/** Identical neutral card motion for every recipient; no resource/hand inputs exist. */
export function theftPose(started: number, now: number, moving = true) {
  const t = clamp((now - started) / THEFT_MS);
  return { position: [(.5 - t) * .36, .95 + Math.sin(t * Math.PI) * .22, .06] as Point3D,
    rotation: [-.12, .3 * Math.sin(t * Math.PI), .08 * Math.sin(t * Math.PI)] as Point3D,
    scale: Math.min(1, t * 6, (1 - t) * 5), visible: moving && t < 1 };
}
