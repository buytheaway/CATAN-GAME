import { PLAYER_COLORS } from "../board/constants";

export const TERRAIN_STYLES = {
  forest: { color: "#4b995b", side: "#327044", hint: "trees" },
  hills: { color: "#d78161", side: "#a95940", hint: "clay" },
  pasture: { color: "#a6cf74", side: "#75984e", hint: "sheep" },
  fields: { color: "#e7c56c", side: "#b19448", hint: "wheat" },
  mountains: { color: "#a6b5c4", side: "#728493", hint: "peaks" },
  desert: { color: "#e5d3a7", side: "#bfa979", hint: "dunes" },
  sea: { color: "#6cb9d3", side: "#41839b", hint: "waves" },
  gold: { color: "#bba363", side: "#87733f", hint: "gold" },
} as const;

export function terrainStyle(terrain: string): { color: string; side: string; hint: string } {
  return TERRAIN_STYLES[terrain as keyof typeof TERRAIN_STYLES]
    ?? { color: "#b5bec5", side: "#7c8791", hint: "none" };
}

export function playerColor(owner: number): string {
  return PLAYER_COLORS[owner] ?? "#ffffff";
}

export function portAppearance(kind: string) {
  const resource = kind.split(":")[2];
  const colors: Record<string, string> = {
    wood: "#4b995b", brick: "#d78161", sheep: "#a6cf74", wheat: "#e7c56c", ore: "#a6b5c4",
  };
  return kind.includes("3:1")
    ? { label: "3:1", color: "#f6f3e9" }
    : { label: `2:1\n${resource ?? "?"}`, color: colors[resource] ?? "#f6f3e9" };
}
