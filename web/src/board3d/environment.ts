import type { BoardRenderModel, BoardSnapshot, Point3D } from "./types";

/** Used on every scenery mesh: decoration is never a tile, edge or vertex target. */
export const ignoreSceneryRaycast = () => undefined;

export function decorativeShipsEnabled(state: BoardSnapshot) {
  return state.tiles.length > 0 && !state.rules_config?.enable_seafarers
    && !state.tiles.some(t => t.terrain === "sea")
    && !Object.keys(state.occupied_ships).length && state.pirate_tile == null;
}

/** Actual tile extent, plus clearance for the entire boat. Excluded from camera/game bounds. */
export function oceanClearance({ tiles, bounds }: Pick<BoardRenderModel, "tiles" | "bounds">) {
  return Math.max(1, ...tiles.map(t => Math.hypot(t.position[0] - bounds.center[0], t.position[2] - bounds.center[2]) + 1)) + .65;
}

const ROUTES = [
  { phase: .25, speed: .009, x: 1.05, z: 1.12 },
  { phase: 2.7, speed: -.0065, x: 1.18, z: 1.02 },
  { phase: 4.65, speed: .0075, x: 1.08, z: 1.18 },
] as const;

/** Seconds are visual animation time, not a game clock. All paths stay outside the tile envelope. */
export function ambientBoatPose(center: Point3D, clearance: number, boat: number, seconds: number) {
  const route = ROUTES[boat % ROUTES.length];
  const angle = route.phase + seconds * route.speed;
  const radius = clearance + .14 * (1 + Math.sin(angle * 2 + route.phase));
  const position: Point3D = [center[0] + Math.cos(angle) * radius * route.x, .025,
    center[2] + Math.sin(angle) * radius * route.z];
  const rotation = -Math.atan2(Math.cos(angle) * route.z * route.speed, -Math.sin(angle) * route.x * route.speed);
  return { position, rotation };
}
