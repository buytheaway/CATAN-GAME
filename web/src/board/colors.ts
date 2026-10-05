import { PLAYER_COLORS } from "./constants";

export const ROOM_COLORS: Record<string, string> = {
  red: "#ef4444", blue: "#3b82f6", orange: "#f59e0b", white: "#f2f4f8",
  green: "#22c55e", purple: "#a855f7",
};

export function colorForPlayer(pid: number, players?: { pid: number; color?: string | null }[]): string {
  const color = players?.find(p => p.pid === pid)?.color;
  return color && ROOM_COLORS[color] || PLAYER_COLORS[pid] || "#ffffff";
}
