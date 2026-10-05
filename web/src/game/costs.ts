import type { ResourceCounts } from "./actions";

/** Presentation only. The Python COST table/executor remains authoritative. */
export const ACTION_COSTS = {
  road: { wood: 1, brick: 1 },
  settlement: { wood: 1, brick: 1, sheep: 1, wheat: 1 },
  city: { wheat: 2, ore: 3 },
  ship: { wood: 1, sheep: 1 },
  dev: { sheep: 1, wheat: 1, ore: 1 },
} satisfies Record<string, ResourceCounts>;

export type CostAction = keyof typeof ACTION_COSTS;
export function costPreview(action: CostAction, hand: Record<string, number>, free = false) {
  if (free) return [];
  return Object.entries(ACTION_COSTS[action]).map(([resource, quantity]) => ({
    resource, quantity, available: (hand[resource] ?? 0) >= quantity,
  }));
}
