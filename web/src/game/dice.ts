export type DiceFaces = [number, number];
export type DiceRollVisual = { id: string; faces: DiceFaces; startedAt: number };
export const DICE_DURATION_MS = 950;

export const DIE_PIPS: Record<number, [number, number][]> = {
  1: [[0, 0]],
  2: [[-1, -1], [1, 1]],
  3: [[-1, -1], [0, 0], [1, 1]],
  4: [[-1, -1], [1, -1], [-1, 1], [1, 1]],
  5: [[-1, -1], [1, -1], [0, 0], [-1, 1], [1, 1]],
  6: [[-1, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [1, 1]],
};

/** No sum splitting or generated fallback faces. */
export function serverDice(value: unknown): DiceFaces | null {
  return Array.isArray(value) && value.length === 2 && value.every(v => Number.isInteger(v) && v >= 1 && v <= 6)
    ? [value[0], value[1]] : null;
}

export function isNewRoll(previous: { key: string; count: number } | null, key: string, count: number) {
  return !!previous && previous.key === key && Number.isInteger(count) && count > previous.count;
}

/** Fixed cube-face convention: +Y=1, +Z=2, +X=3, -X=4, -Z=5, -Y=6. */
export function finalDieRotation(face: number): [number, number, number] {
  const half = Math.PI / 2;
  return ({ 1: [0, 0, 0], 2: [-half, 0, 0], 3: [0, 0, half],
    4: [0, 0, -half], 5: [half, 0, 0], 6: [Math.PI, 0, 0] } as Record<number, [number, number, number]>)[face];
}

/** Finite deterministic choreography of a KNOWN face. It never produces a gameplay result. */
export function diePose(progress: number, face: number, side: number) {
  const t = Math.max(0, Math.min(1, progress)), remaining = (1 - t) ** 3;
  const final = finalDieRotation(face);
  return {
    position: [(side ? 1 : -1) * (0.62 + remaining * 1.1),
      1.25 + Math.sin(t * Math.PI) * 1.35 + Math.abs(Math.sin(t * Math.PI * 3)) * (1 - t) * 0.3,
      0.7 + remaining * 0.65] as [number, number, number],
    rotation: [final[0] + remaining * Math.PI * 6, final[1] + remaining * Math.PI * 4,
      final[2] + remaining * Math.PI * (side ? -4 : 4)] as [number, number, number],
  };
}
