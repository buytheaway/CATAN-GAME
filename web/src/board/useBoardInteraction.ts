import { useEffect, useRef, useState } from "react";
import type { Command, GameState } from "../components/BoardView.types";
import { createBoardInteraction, emptySelection, reconcileSelection } from "./interaction";

export function useBoardInteraction(state: GameState, pid: number, matchKey: string, error: unknown,
  send: (command: Command) => void) {
  const [selection, change] = useState(emptySelection);
  const previousKey = useRef(matchKey);
  useEffect(() => {
    const newMatch = previousKey.current !== matchKey;
    previousKey.current = matchKey;
    change(current => newMatch ? emptySelection()
      : error ? { ...current, shipSource: null, victim: null, waiting: false }
      : reconcileSelection(current, state, pid));
  }, [state, pid, matchKey, error]);
  return createBoardInteraction(state, pid, previousKey.current === matchKey ? selection : emptySelection(), change, send);
}
