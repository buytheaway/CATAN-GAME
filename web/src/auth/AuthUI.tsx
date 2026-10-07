import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AuthFailure, authRequest, errorText, getActiveGames, getMe, type User } from "./api";
import { removeRecentGame, type RecentGame, type GameSummary } from "../recentGames";
import type { WSClient } from "../wsClient";
import "./auth.css";

type Auth = { user: User | null; loading: boolean; message: string; revision: number;
  signIn: (register: boolean, data: Record<string, string>) => Promise<void>;
  logout: () => Promise<void>; claim: (binding: RecentGame) => Promise<void>; refresh: () => Promise<void>; client: WSClient };
const Context = createContext<Auth | null>(null);
export const useAuth = () => useContext(Context);
const describe = (e: unknown) => errorText[e instanceof AuthFailure ? e.code : "persistence_unavailable"];

export function AuthProvider({ client, onExit, children }: {client: WSClient; onExit: () => void; children: ReactNode}) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const refresh = async () => {
    const request = ++generation.current;
    try { const me = await getMe(); if (request === generation.current) { setUser(me.authenticated ? me.user ?? null : null); setMessage(""); } }
    catch (e) { if (request === generation.current) setMessage(describe(e)); }
    finally { if (request === generation.current) setLoading(false); }
  };
  useEffect(() => { void refresh(); }, []);
  const signIn = async (register: boolean, data: Record<string, string>) => {
    ++generation.current;
    const result = await authRequest<{user: User}>(`/api/auth/${register ? "register" : "login"}`, data);
    ++generation.current; setLoading(false); setUser(result.user); setMessage(""); setRevision(n => n + 1);
    // A current guest socket stays alive until the explicit claim action.
    if (!client.roomState) client.leaveRoom();
  };
  const logout = async () => {
    ++generation.current;
    await authRequest("/api/auth/logout", {});
    ++generation.current; setUser(null); setLoading(false); setMessage(""); client.leaveRoom(); onExit();
  };
  const claim = async (binding: RecentGame) => {
    const current = client.guestBinding();
    await authRequest("/api/games/claim", { room_code: binding.room_code, reconnect_token: binding.reconnect_token,
      ...(current?.room_code === binding.room_code && client.connectionNonce ? {connection_nonce: client.connectionNonce} : {}) });
    removeRecentGame(binding); setRevision(n => n + 1); setMessage("");
  };
  return <Context.Provider value={{user, loading, message, revision, signIn, logout, claim, refresh, client}}>{children}</Context.Provider>;
}

export function AccountControls() {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("input,button")?.focus();
    return () => previous?.focus();
  }, [open, register, auth?.user]);
  if (!auth) return null;
  const close = () => { if (!busy) { setOpen(false); setPassword(""); setError(""); } };
  const perform = async (operation: () => Promise<void>, leave = true) => {
    setBusy(true); setError("");
    try { await operation(); setPassword(""); if (leave) setOpen(false); }
    catch (e) { setError(describe(e)); }
    finally { setBusy(false); }
  };
  const binding = auth.client.guestBinding();
  return <div className="auth-controls">
    <button className="auth-launch" title={auth.user?.display_name} onClick={() => { setOpen(true); void auth.refresh(); }}>
      {auth.user ? auth.user.display_name : "Sign In"}</button>
    {open && createPortal(<div className="auth-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}>
      <div className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title" ref={panel}
        onKeyDown={e => {
          if (e.key === "Escape") close();
          if (e.key === "Tab") {
            const nodes = Array.from(panel.current?.querySelectorAll<HTMLElement>("input:not(:disabled),button:not(:disabled)") ?? []);
            const first = nodes[0], last = nodes[nodes.length - 1];
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
          }
        }}>
        <div className="auth-heading"><h3 id="auth-title">{auth.user ? "Account" : register ? "Create account" : "Sign In"}</h3>
          <button onClick={close} disabled={busy} aria-label="Close account">×</button></div>
        {auth.user ? <>
          <p>{auth.user.display_name} <span className="auth-muted">@{auth.user.username}</span></p>
          {binding && <><p>This game is currently saved only on this browser.</p>
            <button disabled={busy} onClick={() => void perform(() => auth.claim(binding))}>Save to account</button></>}
          <button disabled={busy} onClick={() => void perform(auth.logout)}>Logout</button>
        </> : <form onSubmit={e => { e.preventDefault(); void perform(() => auth.signIn(register,
          {username, password, ...(register ? {display_name: displayName} : {})})); }}>
          <label>Username<input autoComplete="username" value={username} maxLength={32} required disabled={busy}
            onChange={e => setUsername(e.target.value)} /></label>
          {register && <label>Display name<input autoComplete="nickname" value={displayName} maxLength={32} required disabled={busy}
            onChange={e => setDisplayName(e.target.value)} /></label>}
          <label>Password<input type="password" autoComplete={register ? "new-password" : "current-password"} value={password}
            minLength={10} maxLength={128} required disabled={busy} onChange={e => setPassword(e.target.value)} /></label>
          <button disabled={busy || auth.loading}>{busy ? "Please wait…" : register ? "Register" : "Login"}</button>
          <button type="button" disabled={busy} onClick={() => { setRegister(!register); setError(""); setPassword(""); }}>
            {register ? "Already have an account? Sign In" : "Create account"}</button>
          <p className="auth-muted">You can also play as a guest.</p>
        </form>}
        {(error || auth.message) && <p role="alert">{error || auth.message}</p>}
      </div>
    </div>, document.body)}
  </div>;
}

export function AccountGames() {
  const auth = useAuth();
  const [games, setGames] = useState<GameSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let mounted = true;
    if (!auth?.user) { setGames([]); return; }
    setLoading(true); setError("");
    getActiveGames().then(result => { if (mounted) setGames(result.games); })
      .catch(e => { if (mounted) setError(describe(e)); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [auth?.user?.username, auth?.revision, retry]);
  if (!auth?.user) return null;
  return <section className="account-games" aria-label="My active games" aria-busy={loading}>
    <div className="auth-heading"><h3>My Active Games</h3><button disabled={loading} onClick={() => setRetry(n => n + 1)}>Check again</button></div>
    {loading && <p>Checking games…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && !games.length && <p>No active account games yet. Create, Join or save a guest game.</p>}
    <div className="recent-games-list">{games.map(game => <article className="recent-game" key={game.room_code}>
      <div className="recent-game-heading"><strong>Room {game.room_code}</strong><span>{game.status === "active" ? "In Game" : game.status === "game_over" ? "Game Over" : "Lobby"}</span></div>
      <p>{game.map_name}</p><p>Your seat: {game.own_name} · {game.player_count}/{game.max_players} players</p>
      {game.winner && <p>Winner: {game.winner.name}</p>}
      <button disabled={loading || !game.can_continue} onClick={() => auth.client.continueAccount(game.room_code, game.own_name)}>
        {game.status === "game_over" ? "Return to Room" : "Continue"}</button>
    </article>)}</div>
  </section>;
}
