import { useEffect, useState } from "react";
import type { ServerError, WSClient } from "../wsClient";
import { defaultWebSocketUrl } from "../wsClient";
import { inspectRecentGames, recentGamesForServer, removeRecentGame, updateRecentName } from "../recentGames";
import type { Inspection, RecentGame } from "../recentGames";
import { colorForPlayer } from "../board/colors";
import "./recentGames.css";

export type RecentCard = { binding: RecentGame; inspection: Inspection | null };

// Separate the small view from discovery so it can be verified without a WebSocket or WebGL.
export function RecentGamesCards({ cards, loading, onContinue }: {
  cards: RecentCard[]; loading: boolean; onContinue: (entry: RecentGame) => void;
}) {
  return <div className="recent-games-list">
    {cards.map(({ binding, inspection }, i) => {
      const game = inspection?.status === "available" ? inspection.game : null;
      return <article className="recent-game" key={`${binding.room_code}:${i}`}>
        <div className="recent-game-heading"><strong>Room {binding.room_code}</strong>
          <span>{loading ? "Checking…" : game ? { lobby: "Lobby", active: "In Game", game_over: "Game Over" }[game.status]
            : "Temporarily unavailable"}</span></div>
        {game && <>
          <p className="recent-map">{game.map_name}</p>
          <p><span className="color-dot" style={{ background: colorForPlayer(0, [{ pid: 0, color: game.own_color }]) }} />
            Player: {game.own_name} · {game.player_count}/{game.max_players} players · {game.connected_count} online</p>
          {game.winner && <p>Winner: {game.winner.name}</p>}
        </>}
        {!loading && !game && <p>Your saved place is kept. Try again when the server is available.</p>}
        <button className="btn primary" disabled={loading || !game?.can_continue} onClick={() => onContinue(binding)}>
          {game?.status === "game_over" ? "Return to Room" : "Continue"}
        </button>
      </article>;
    })}
  </div>;
}

export async function discoverRecentGames(signal?: AbortSignal, url = defaultWebSocketUrl()): Promise<RecentCard[]> {
  const bindings = recentGamesForServer(url);
  if (!bindings.length) return [];
  try {
    const results = await inspectRecentGames(bindings, signal);
    if (signal?.aborted) return [];
    const cards: RecentCard[] = [];
    results.forEach((inspection, i) => {
      const binding = bindings[i];
      if (inspection.status === "invalid") removeRecentGame(binding);
      else {
        if (inspection.status === "available") updateRecentName(binding, inspection.game.own_name);
        cards.push({ binding: { ...binding, last_known_name: inspection.status === "available" ? inspection.game.own_name : binding.last_known_name }, inspection });
      }
    });
    return cards;
  } catch {
    return bindings.map(binding => ({ binding, inspection: { status: "temporarily_unavailable" } }));
  }
}

export default function RecentGames({ client, wsDefault, error }: {
  client: WSClient; wsDefault: string; error: ServerError | null;
}) {
  const [cards, setCards] = useState<RecentCard[]>(() => recentGamesForServer(wsDefault).map(binding => ({ binding, inspection: null })));
  const [loading, setLoading] = useState(cards.length > 0);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    const timeout = window.setTimeout(() => abort.abort(), 8000);
    let mounted = true;
    setLoading(recentGamesForServer(wsDefault).length > 0);
    discoverRecentGames(abort.signal, wsDefault).then(next => {
      window.clearTimeout(timeout);
      if (mounted) { setCards(next); setLoading(false); }
    });
    return () => { mounted = false; abort.abort(); window.clearTimeout(timeout); };
  }, [retry, error, wsDefault]);
  return <section className="recent-games" aria-label="Recent games" aria-busy={loading}>
    {cards.length > 0 && <>
      <div className="recent-games-title"><h3>Continue Game</h3>
        <button className="btn" disabled={loading} onClick={() => setRetry(n => n + 1)}>Check again</button></div>
      <RecentGamesCards cards={cards} loading={loading} onContinue={binding => client.continueGame(binding, wsDefault)} />
    </>}
    <p className="guest-recovery-note">Guest games are recoverable only on this browser.</p>
  </section>;
}
