import { useEffect, useState } from "react";
import type { ServerError, WSClient } from "../wsClient";
import { defaultWebSocketUrl } from "../wsClient";
import { inspectRecentGames, recentGamesForServer, removeRecentGame, updateRecentName } from "../recentGames";
import type { Inspection, RecentGame } from "../recentGames";
import GameCard from "../shell/GameCard";
import { EmptyState, SectionHeader } from "../shell/PageShell";
import "./recentGames.css";
import { useAuth } from "../auth/AuthUI";

export type RecentCard = { binding: RecentGame; inspection: Inspection | null };

// Separate the small view from discovery so it can be verified without a WebSocket or WebGL.
export function RecentGamesCards({ cards, loading, onContinue, onSave }: {
  cards: RecentCard[]; loading: boolean; onContinue: (entry: RecentGame) => void; onSave?: (entry: RecentGame) => void;
}) {
  return <div className="recent-games-list">
    {cards.map(({ binding, inspection }, i) => {
      const game = inspection?.status === "available" ? inspection.game : null;
      return <GameCard key={`${binding.room_code}:${i}`} code={binding.room_code} game={game} loading={loading}
        onContinue={() => onContinue(binding)} onSave={onSave ? () => onSave(binding) : undefined} />;
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
  const auth = useAuth();
  const [claimError, setClaimError] = useState("");
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
  }, [retry, error, wsDefault, auth?.revision]);
  return <section className="recent-games" aria-label="Recent games" aria-busy={loading}>
    {cards.length > 0 && <>
      <SectionHeader title="Continue Game" eyebrow="Saved on this browser">
        <button className="btn subtle" disabled={loading} onClick={() => setRetry(n => n + 1)}>Check again</button></SectionHeader>
      <RecentGamesCards cards={cards} loading={loading} onContinue={binding => client.continueGame(binding, wsDefault)}
        onSave={auth?.user ? binding => { setClaimError(""); void auth.claim(binding).catch(() => setClaimError("Could not save this guest game. Check your session and try again.")); } : undefined} />
      {claimError && <p role="alert">{claimError}</p>}
    </>}
    {!loading && !cards.length && !auth?.user && <EmptyState title="No saved tables yet">
      Host a game or join your friends. Your recoverable rooms will appear here.
    </EmptyState>}
    <p className="guest-recovery-note">Guest games are recoverable only on this browser.</p>
  </section>;
}
