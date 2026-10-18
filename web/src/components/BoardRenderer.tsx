import { Component, lazy, Suspense, useMemo, useState } from "react";
import type { ReactNode } from "react";
import BoardView from "./BoardView";
import type { BoardViewProps } from "./BoardView.types";
import "../board3d/board3d.css";
import type { DiceRollVisual } from "../game/dice";
import { FOG_REVEAL_MS, useFogReveal } from "../board/fogReveal";
import { FOG_3D_REVEAL_MS } from "../board3d/fogPresentation";
import { useShipFeedback, type ShipEvent } from "../board/shipFeedback";
import { usePieceFeedback } from "../board3d/pieceFeedback";

const Board3D = lazy(() => import("../board3d/Board3D"));

class Board3DErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed
      ? <div className="board3d-fallback" role="alert">The 3D board could not start. Switch to 2D to continue.</div>
      : this.props.children;
  }
}

export default function BoardRenderer(props: BoardViewProps & { diceRoll?: DiceRollVisual | null; matchKey?: string; connected?: boolean; tick?: number; events?: readonly ShipEvent[] }) {
  const [mode, setMode] = useState<"2d" | "3d">("3d");
  const [shipsAnimated, setShipsAnimated] = useState(true);
  const [constructionAnimated, setConstructionAnimated] = useState(true);
  const events = useMemo(() => (props.events ?? []).filter(e => e.type === "build_ship" || e.type === "move_ship")
    .map(({ id, tick, type, actor_pid }) => ({ id, tick, type, actor_pid })), [props.events]);
  const shipCues = useShipFeedback({ key: props.matchKey ?? "", tick: props.tick ?? 0,
    ships: props.state.occupied_ships, events, connected: props.connected ?? true }, mode === "3d" && shipsAnimated);
  const pieceCues = usePieceFeedback({ key: props.matchKey ?? "", tick: props.tick ?? 0,
    roads: props.state.occupied_e, vertices: props.state.occupied_v, connected: props.connected ?? true }, mode === "3d" && constructionAnimated);
  const reveals = useFogReveal({ key: props.matchKey ?? "", tick: props.tick ?? 0,
    tiles: props.state.tiles, connected: props.connected ?? true }, mode === "3d" ? FOG_3D_REVEAL_MS : FOG_REVEAL_MS);
  return (
    <div className="board-renderer">
      <div className="board-renderer-selector" role="group" aria-label="Board renderer">
        <span>View</span>
        <button type="button" className="game-button" aria-pressed={mode === "2d"} onClick={() => setMode("2d")}>2D</button>
        <button type="button" className="game-button" aria-pressed={mode === "3d"} onClick={() => setMode("3d")}>3D</button>
      </div>
      {mode === "2d" ? <BoardView {...props} reveals={reveals} /> : (
        <Board3DErrorBoundary>
          <Suspense fallback={<div className="board3d-fallback" role="status">Loading 3D board…</div>}>
            <Board3D state={props.state} interaction={props.interaction} diceRoll={props.diceRoll}
              matchKey={props.matchKey} connected={props.connected} reveals={reveals}
              shipCues={shipCues} shipsAnimated={shipsAnimated} onShipsAnimated={setShipsAnimated}
              pieceCues={pieceCues} constructionAnimated={constructionAnimated} onConstructionAnimated={setConstructionAnimated} />
          </Suspense>
        </Board3DErrorBoundary>
      )}
    </div>
  );
}
