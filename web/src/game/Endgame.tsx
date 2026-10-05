import { useEffect, useState } from "react";
import type { RoomState, ServerError } from "../wsClient";
import type { GameSnapshot } from "./presentation";
import { finalStandings, rematchReason } from "./actions";
import GameOverlay from "./GameOverlay";
import { ActionFeedback } from "./TradePanel";

export default function Endgame({ state, pid, room, connected, matchKey, error, onRematch, onLobby }: {
  state: GameSnapshot; pid: number; room: RoomState | null; connected: boolean; matchKey: string;
  error: ServerError | null; onRematch: () => void; onLobby?: () => void;
}) {
  const [waiting, setWaiting] = useState(false);
  // Rematch has no command ACK/replay; a lost connection must allow an explicit retry.
  useEffect(() => setWaiting(false), [error, matchKey, connected]);
  const winner = state.players.find(p => p.pid === state.winner_pid);
  const reason = rematchReason(room, pid, connected);
  return <GameOverlay id="match-results" title="Match results" modal>
    <div className="victory-banner"><span>{winner?.pid === pid ? "Victory" : "Match complete"}</span>
      <h3>{winner?.name ?? "Winner unavailable"}</h3><strong>{winner?.vp ?? "—"} VP</strong></div>
    <ol className="final-standings" aria-label="Final scores">{finalStandings(state).map(p =>
      <li key={p.pid} className={p.pid === state.winner_pid ? "is-winner" : ""}>
        <span>{p.name}{p.pid === state.winner_pid && <small>Winner</small>}</span><strong>{p.vp} VP</strong>
      </li>)}</ol>
    <ActionFeedback error={error} waiting={waiting} />
    {reason && <p>{reason}</p>}
    <div className="result-actions"><button className="game-button primary-action" disabled={waiting || !!reason}
      onClick={() => { setWaiting(true); onRematch(); }}>Rematch</button>
      <button className="game-button" disabled={!onLobby} onClick={onLobby}>Back to Lobby</button></div>
  </GameOverlay>;
}
