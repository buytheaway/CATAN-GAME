import type { GameSummary } from "../recentGames";
import { colorForPlayer } from "../board/colors";
import { StatusBadge } from "./PageShell";

// Presentation only. The caller owns inspection, recovery credentials and Continue.
export default function GameCard({ code, game, loading, onContinue, onSave }: {
  code: string; game: GameSummary | null; loading: boolean; onContinue: () => void; onSave?: () => void;
}) {
  const label = loading ? "Checking…" : game ? { lobby: "Lobby", active: "In Game", game_over: "Game Over" }[game.status]
    : "Temporarily unavailable";
  return <article className="recent-game">
    <div className="recent-game-heading"><strong>Room {code}</strong>
      <StatusBadge tone={game?.status === "active" ? "live" : game?.status === "game_over" ? "warm" : "neutral"}>{label}</StatusBadge></div>
    {game ? <>
      <h4 className="recent-map">{game.map_name}</h4>
      <p className="recent-identity"><span className="color-dot" style={{ background: colorForPlayer(0, [{ pid: 0, color: game.own_color }]) }} />
        <span>Player: <strong>{game.own_name}</strong></span></p>
      <p className="recent-presence">{game.player_count}/{game.max_players} players <span>·</span> {game.connected_count} online</p>
      {game.winner && <p className="recent-winner">Winner: {game.winner.name}</p>}
    </> : <p className="recent-unavailable">{loading ? "Checking your saved place…" : "Your saved place is kept. Try again when the server is available."}</p>}
    <div className="recent-actions"><button className="btn primary" disabled={loading || !game?.can_continue} onClick={onContinue}>
      {game?.status === "game_over" ? "Return to Room" : "Continue"}</button>
      {game && onSave && <button className="btn subtle" disabled={loading} onClick={onSave}>Save to account</button>}
    </div>
  </article>;
}
