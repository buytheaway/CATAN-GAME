import { PLAYER_COLORS } from "../board/constants";

export const TERRAIN_STYLES = {
  forest: { color: "#43825c", side: "#285c43", hint: "trees" },
  hills: { color: "#cc785a", side: "#964c39", hint: "clay" },
  pasture: { color: "#a8ca79", side: "#728e51", hint: "sheep" },
  fields: { color: "#e8ba54", side: "#a78032", hint: "wheat" },
  mountains: { color: "#9baebc", side: "#637b8b", hint: "peaks" },
  desert: { color: "#e8d5ac", side: "#baa078", hint: "dunes" },
  sea: { color: "#347f9b", side: "#22576e", hint: "waves" },
  gold: { color: "#a59055", side: "#6e5d37", hint: "gold" },
} as const;

// Visual accents only; gameplay ownership still uses the existing player palette.
export const VISUAL = {
  background: "#203743", ink: "#202c35", ivory: "#fff7e5", tokenSide: "#c1ac89",
  accent: "#b63831", legal: "#c5f0df", hover: "#ffffff", selected: "#ffc66b",
  tree: "#21563e", treeLight: "#307851", trunk: "#806345", wheat: "#fff0ad",
  fur: "#fff9e9", sheep: "#46544b", clay: "#b05b44", clayLight: "#e49b73",
  peak: "#5d7587", snow: "#e5edf0", sand: "#f1e0bc", sandShade: "#d5bb8b",
  nugget: "#ffda65", nuggetShade: "#c99c35", wave: "#82bdcc", dock: "#b39772",
  pirate: "#25313c", robber: "#303b45",
} as const;

export function targetColor(hovered: boolean, selected = false) {
  return selected ? VISUAL.selected : hovered ? VISUAL.hover : VISUAL.legal;
}

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
    wood: TERRAIN_STYLES.forest.color, brick: TERRAIN_STYLES.hills.color,
    sheep: TERRAIN_STYLES.pasture.color, wheat: TERRAIN_STYLES.fields.color, ore: TERRAIN_STYLES.mountains.color,
  };
  return kind.includes("3:1")
    ? { label: "3:1", color: "#f6f3e9" }
    : { label: `2:1\n${resource ?? "?"}`, color: colors[resource] ?? "#f6f3e9" };
}
