/** Presentation timing only. SVG keeps its existing 420 ms transition. */
export const FOG_3D_REVEAL_MS = 1000;
export const FOG_IDLE_HZ = 12;
export type FogQuality = "mist" | "still" | "simple";

export function fogQuality(requested: FogQuality, reduced: boolean, lowPrecision = false): FogQuality {
  return lowPrecision ? "simple" : reduced && requested === "mist" ? "still" : requested;
}

export function fogProgress(started: number, now: number): number {
  return Math.min(1, Math.max(0, (now - started) / FOG_3D_REVEAL_MS));
}

export function fogDispersal(progress: number) {
  const p = Math.min(1, Math.max(0, progress));
  const eased = p * p * (3 - 2 * p);
  return { opacity: 1 - eased, spread: 1 + eased * .15, lift: eased * .38 };
}
