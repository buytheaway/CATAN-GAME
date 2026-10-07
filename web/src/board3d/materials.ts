import { PLAYER_COLORS } from "../board/constants";
import { RESOURCE_ICON_PATHS } from "../game/resourceIcons";

export const TERRAIN_STYLES = {
  forest: { color: "#377f4c", side: "#235239", hint: "trees" },
  hills: { color: "#c66a43", side: "#8d452f", hint: "clay" },
  pasture: { color: "#8fba63", side: "#657f43", hint: "sheep" },
  fields: { color: "#e3ad38", side: "#a77c29", hint: "wheat" },
  mountains: { color: "#9baebc", side: "#637b8b", hint: "peaks" },
  desert: { color: "#e8d5ac", side: "#baa078", hint: "dunes" },
  sea: { color: "#286b8b", side: "#18465f", hint: "waves" },
  gold: { color: "#a59055", side: "#6e5d37", hint: "gold" },
} as const;

// Visual accents only; gameplay ownership still uses the existing player palette.
export const VISUAL = {
  background: "#0d2333", ink: "#202c35", ivory: "#fff7e5", tokenSide: "#c1ac89",
  accent: "#b63831", legal: "#c5f0df", hover: "#ffffff", selected: "#ffc66b",
  tree: "#194d30", treeLight: "#2c7845", trunk: "#806345", wheat: "#ffe796",
  fur: "#fff9e9", sheep: "#46544b", clay: "#b05b44", clayLight: "#e49b73",
  peak: "#5d7587", snow: "#e5edf0", sand: "#f1e0bc", sandShade: "#d5bb8b",
  nugget: "#ffda65", nuggetShade: "#c99c35", wave: "#82bdcc", dock: "#b39772",
  pirate: "#25313c", robber: "#303b45",
} as const;

export function targetColor(hovered: boolean, selected = false) {
  return selected ? VISUAL.selected : hovered ? VISUAL.hover : VISUAL.legal;
}

const TILE_FEEDBACK = {
  selected: { color: VISUAL.selected, intensity: 0.22 },
  hovered: { color: VISUAL.hover, intensity: 0.12 },
  legal: { color: VISUAL.legal, intensity: 0.045 },
} as const;

/** Illuminate the existing surface, without a second hex or shared-material mutation. */
export function tileFeedback(hovered: boolean, legal: boolean, selected: boolean) {
  return selected ? TILE_FEEDBACK.selected : hovered ? TILE_FEEDBACK.hovered : legal ? TILE_FEEDBACK.legal : undefined;
}

/** Stable visual variety only. No game seed, randomness, IDs or snapshot changes. */
export function terrainVariation(tileIndex: number) {
  const phase = (Math.imul(tileIndex + 1, 2654435761) >>> 0) / 0xffffffff;
  return {
    rotation: (phase - 0.5) * 0.32,
    scale: 0.94 + phase * 0.12,
    offset: (phase - 0.5) * 0.06,
    height: 0.88 + ((tileIndex * 7 + 3) % 11) / 10 * 0.24,
  };
}

export function terrainStyle(terrain: string): { color: string; side: string; hint: string } {
  return TERRAIN_STYLES[terrain as keyof typeof TERRAIN_STYLES]
    ?? { color: "#b5bec5", side: "#7c8791", hint: "none" };
}

export function playerColor(owner: number): string {
  return PLAYER_COLORS[owner] ?? "#ffffff";
}

export function portAppearance(kind: string) {
  const name = kind.split(":")[2];
  const resource = Object.prototype.hasOwnProperty.call(RESOURCE_ICON_PATHS, name) ? name as keyof typeof RESOURCE_ICON_PATHS : undefined;
  const colors: Record<string, string> = {
    wood: TERRAIN_STYLES.forest.color, brick: TERRAIN_STYLES.hills.color,
    sheep: TERRAIN_STYLES.pasture.color, wheat: TERRAIN_STYLES.fields.color, ore: TERRAIN_STYLES.mountains.color,
  };
  return kind === "3:1"
    ? { label: "3:1", resource: undefined, color: VISUAL.dock }
    : { label: kind.startsWith("2:1:") ? "2:1" : "?", resource, color: colors[resource ?? ""] ?? VISUAL.dock };
}
