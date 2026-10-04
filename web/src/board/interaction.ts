import type { Command, EdgeTuple, GameState } from "../components/BoardView.types";
import { edgeId } from "./constants";

export type VictimChoice = { type: "move_robber" | "move_pirate"; tile: number; victims: number[] };
export type BoardSelection = {
  action: string | null; shipSource: EdgeTuple | null; victim: VictimChoice | null; waiting: boolean;
};
export const emptySelection = (): BoardSelection => ({ action: null, shipSource: null, victim: null, waiting: false });
export type BoardTargets = { vertices: number[]; edges: EdgeTuple[]; sources: EdgeTuple[]; tiles: number[] };

export function interactionTargets(state: GameState, pid: number, selection: BoardSelection) {
  const legal = state.legal?.pid === pid ? state.legal : undefined;
  const movement = !!(legal?.robber_tiles?.length || legal?.pirate_tiles?.length);
  const action = movement
    ? (["robber", "pirate"].includes(selection.action ?? "") ? selection.action : null)
    : state.phase === "setup" ? state.setup_need === "settlement" ? "settlement" : "road" : selection.action;
  const targets: BoardTargets = { vertices: [], edges: [], sources: [], tiles: [] };
  if (!legal || selection.waiting || selection.victim) return { action, targets };
  if (movement) {
    targets.tiles = [...(action === "pirate" ? [] : legal.robber_tiles ?? []),
                     ...(action === "robber" ? [] : legal.pirate_tiles ?? [])];
  } else if (action === "settlement") targets.vertices = legal.settlements;
  else if (action === "city") targets.vertices = legal.cities;
  else if (action === "road") targets.edges = legal.roads;
  else if (action === "ship") targets.edges = legal.ships;
  else if (action === "move_ship") {
    targets.sources = legal.move_ship?.sources ?? [];
    targets.edges = selection.shipSource ? legal.move_ship?.targets[edgeId(selection.shipSource)] ?? [] : targets.sources;
  }
  return { action, targets };
}

/** UI policy only: membership in server lists, selection and existing payloads. */
export function createBoardInteraction(state: GameState, pid: number, selection: BoardSelection,
  change: (selection: BoardSelection) => void, send: (command: Command) => void) {
  const { action, targets } = interactionTargets(state, pid, selection);
  const legal = state.legal?.pid === pid ? state.legal : undefined;
  const submit = (command: Command) => {
    change({ ...selection, shipSource: null, victim: null, waiting: true });
    send(command);
  };
  return {
    action, targets, selection, legal,
    onSelectAction(next: string | null) {
      change({ ...selection, action: next, shipSource: null, victim: null });
    },
    onVertexClick(vid: number) {
      if (!targets.vertices.includes(vid)) return;
      if (action === "city") submit({ type: "upgrade_city", vid });
      else if (action === "settlement") submit({ type: "place_settlement", vid, setup: state.phase === "setup" });
    },
    onEdgeClick(edge: EdgeTuple) {
      const target = targets.edges.find(e => edgeId(e) === edgeId(edge));
      if (action === "move_ship" && selection.shipSource && edgeId(edge) === edgeId(selection.shipSource)) {
        change({ ...selection, shipSource: null });
        return;
      }
      if (!target) return;
      if (action === "road") submit({ type: "place_road", eid: target, setup: state.phase === "setup",
        ...(legal?.road_free ? { free: true } : {}) });
      else if (action === "ship") submit({ type: "build_ship", eid: target });
      else if (action === "move_ship") {
        if (selection.shipSource) submit({ type: "move_ship", from_eid: selection.shipSource, to_eid: target });
        else change({ ...selection, shipSource: target });
      }
    },
    onTileClick(tile: number) {
      if (!targets.tiles.includes(tile)) return;
      const pirate = !!legal?.pirate_tiles?.includes(tile);
      const type = pirate ? "move_pirate" : "move_robber";
      const victims = (pirate ? legal?.pirate_victims : legal?.robber_victims)?.[tile] ?? [];
      if (victims.length > 1) change({ ...selection, victim: { type, tile, victims } });
      else submit({ type, tile, ...(victims.length ? { victim: victims[0] } : {}) });
    },
    onVictimClick(pid: number) {
      const choice = selection.victim;
      const current = choice?.type === "move_pirate" ? legal?.pirate_victims : legal?.robber_victims;
      if (choice && !selection.waiting && choice.victims.includes(pid) && current?.[choice.tile]?.includes(pid)) {
        submit({ type: choice.type, tile: choice.tile, victim: pid });
      }
    },
    onCancel() { change({ ...selection, shipSource: null, victim: null }); },
  };
}

export type BoardInteraction = ReturnType<typeof createBoardInteraction>;

export function reconcileSelection(selection: BoardSelection, state: GameState, pid: number): BoardSelection {
  const legal = state.legal?.pid === pid ? state.legal : undefined;
  const shipSource = selection.shipSource && legal?.move_ship?.sources.some(e => edgeId(e) === edgeId(selection.shipSource!))
    ? selection.shipSource : null;
  const choice = selection.victim;
  const tiles = choice?.type === "move_pirate" ? legal?.pirate_tiles : legal?.robber_tiles;
  const victims = choice?.type === "move_pirate" ? legal?.pirate_victims : legal?.robber_victims;
  const victim = choice && tiles?.includes(choice.tile) ? { ...choice, victims: victims?.[choice.tile] ?? [] } : null;
  return { ...selection, shipSource, victim: victim?.victims.length ? victim : null, waiting: false };
}
