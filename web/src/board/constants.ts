import type { EdgeTuple } from "../components/BoardView.types";

export const PLAYER_COLORS = [
  "#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#14b8a6",
] as const;

export function edgeId([a, b]: EdgeTuple): string {
  return a < b ? `${a},${b}` : `${b},${a}`;
}
