import { Component, lazy, Suspense, useState } from "react";
import type { ReactNode } from "react";
import BoardView from "./BoardView";
import type { BoardViewProps } from "./BoardView.types";
import "../board3d/board3d.css";
import type { DiceRollVisual } from "../game/dice";

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

export default function BoardRenderer(props: BoardViewProps & { diceRoll?: DiceRollVisual | null }) {
  const [mode, setMode] = useState<"2d" | "3d">("3d");
  return (
    <div className="board-renderer">
      <div className="board-renderer-selector" role="group" aria-label="Board renderer">
        <span>View</span>
        <button type="button" className="game-button" aria-pressed={mode === "2d"} onClick={() => setMode("2d")}>2D</button>
        <button type="button" className="game-button" aria-pressed={mode === "3d"} onClick={() => setMode("3d")}>3D</button>
      </div>
      {mode === "2d" ? <BoardView {...props} /> : (
        <Board3DErrorBoundary>
          <Suspense fallback={<div className="board3d-fallback" role="status">Loading 3D board…</div>}>
            <Board3D state={props.state} interaction={props.interaction} diceRoll={props.diceRoll} />
          </Suspense>
        </Board3DErrorBoundary>
      )}
    </div>
  );
}
