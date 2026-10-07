import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AuthFailure, authRequest, errorText, getActiveGames, getMe, type User } from "./api";
import { removeRecentGame, type RecentGame, type GameSummary } from "../recentGames";
import type { WSClient } from "../wsClient";
import GameCard from "../shell/GameCard";
import { EmptyState, SectionHeader } from "../shell/PageShell";
import { authErrorField, validateAuth, type AuthField, type AuthFieldErrors } from "./validation";
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

export function AccountControls({ shell = false }: { shell?: boolean }) {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState<Partial<Record<AuthField, boolean>>>({});
  const [serverErrors, setServerErrors] = useState<AuthFieldErrors>({});
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    (panel.current?.querySelector<HTMLElement>("input:not(:disabled)") ?? panel.current?.querySelector<HTMLElement>("button:not(:disabled)"))?.focus();
    return () => previous?.focus();
  }, [open, register, auth?.user]);
  useEffect(() => {
    if (!open) return;
    if (busy) { panel.current?.focus(); return; }
    const field = Object.keys(serverErrors).find(key => serverErrors[key as AuthField]);
    if (field) panel.current?.querySelector<HTMLInputElement>(`input[name="${field}"]`)?.focus();
  }, [open, busy, serverErrors]);
  if (!auth) return null;
  const close = () => { if (!busy) { setOpen(false); setPassword(""); setError(""); setTouched({}); setServerErrors({}); } };
  const fields = { username, password, display_name: displayName };
  const validation = validateAuth(fields, register);
  const fieldError = (field: AuthField) => serverErrors[field] || (touched[field] ? validation[field] : undefined);
  const edit = (field: AuthField, value: string) => {
    if (field === "username") setUsername(value);
    else if (field === "password") setPassword(value);
    else setDisplayName(value);
    setServerErrors(previous => ({ ...previous, [field]: undefined })); setError("");
  };
  const perform = async (operation: () => Promise<void>, leave = true) => {
    setBusy(true); setError(""); setServerErrors({});
    try { await operation(); setPassword(""); setTouched({}); if (leave) setOpen(false); }
    catch (e) {
      const field = e instanceof AuthFailure ? authErrorField(e.code) : undefined;
      if (field) setServerErrors({ [field]: describe(e) });
      else setError(describe(e));
    }
    finally { setBusy(false); }
  };
  const binding = auth.client.guestBinding();
  return <div className={`auth-controls${shell ? " auth-controls--shell" : ""}`}>
    {shell && <span className="shell-account-label">{auth.loading ? "Checking account…" : auth.user ? "Signed in" : "Playing as a guest"}</span>}
    <button className="auth-launch" title={auth.user?.display_name} onClick={() => {
      if (!auth.user) setRegister(false);
      setTouched({}); setServerErrors({}); setError(""); setOpen(true); void auth.refresh();
    }}>
      {auth.user ? auth.user.display_name : "Sign In"}</button>
    {open && createPortal(<div className="auth-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}>
      <div className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title" aria-busy={busy || auth.loading} tabIndex={-1} ref={panel}
        onKeyDown={e => {
          if (e.key === "Escape") close();
          if (e.key === "Tab") {
            const nodes = Array.from(panel.current?.querySelectorAll<HTMLElement>("input:not(:disabled),button:not(:disabled)") ?? []);
            const first = nodes[0], last = nodes[nodes.length - 1];
            if (!nodes.length) { e.preventDefault(); panel.current?.focus(); }
            else if (document.activeElement === panel.current) { e.preventDefault(); (e.shiftKey ? last : first)?.focus(); }
            else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
          }
        }}>
        <div className="auth-heading"><div><p className="shell-eyebrow">Your place at the table</p><h3 id="auth-title">{auth.user ? "Account" : register ? "Create account" : "Sign In"}</h3></div>
          <button onClick={close} disabled={busy} aria-label="Close account">×</button></div>
        {auth.user ? <>
          <p className="auth-account-name">{auth.user.display_name} <span className="auth-muted">@{auth.user.username}</span></p>
          {binding && <><p>This game is currently saved only on this browser.</p>
            <button disabled={busy} onClick={() => void perform(() => auth.claim(binding))}>Save to account</button></>}
          <button disabled={busy} onClick={() => void perform(auth.logout)}>Logout</button>
        </> : <form noValidate onSubmit={e => {
          e.preventDefault(); setTouched({ username: true, password: true, display_name: register }); setServerErrors({}); setError("");
          const invalid = Object.keys(validation)[0];
          if (invalid) { panel.current?.querySelector<HTMLInputElement>(`input[name="${invalid}"]`)?.focus(); return; }
          void perform(() => auth.signIn(register, { username, password, ...(register ? { display_name: displayName } : {}) }));
        }}>
          <p className="auth-intro">{register ? "Keep your games with one account, across browsers." : "Sign in to return to your account games."}</p>
          <div className="auth-field"><label htmlFor="auth-username">Username</label>
            <input id="auth-username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} required disabled={busy}
              aria-invalid={!!fieldError("username")} aria-describedby={`auth-username-help${fieldError("username") ? " auth-username-error" : ""}`}
              onBlur={() => setTouched(previous => ({ ...previous, username: true }))} onChange={e => edit("username", e.target.value)} />
            <p className="auth-muted" id="auth-username-help">3–32 ASCII letters (A–Z), digits, _ or -. Use your username, not an email or display name. Uppercase and lowercase are equivalent.</p>
            {fieldError("username") && <p className="auth-field-error" id="auth-username-error" role="alert">{fieldError("username")}</p>}
          </div>
          {register && <div className="auth-field"><label htmlFor="auth-display-name">Display name</label>
            <input id="auth-display-name" name="display_name" autoComplete="nickname" value={displayName} required disabled={busy}
              aria-invalid={!!fieldError("display_name")} aria-describedby={`auth-display-help${fieldError("display_name") ? " auth-display-error" : ""}`}
              onBlur={() => setTouched(previous => ({ ...previous, display_name: true }))} onChange={e => edit("display_name", e.target.value)} />
            <p className="auth-muted" id="auth-display-help">Shown to other players. 1–32 characters; Unicode names are welcome. This is separate from your sign-in username.</p>
            {fieldError("display_name") && <p className="auth-field-error" id="auth-display-error" role="alert">{fieldError("display_name")}</p>}
          </div>}
          <div className="auth-field"><label htmlFor="auth-password">Password</label>
            <input id="auth-password" name="password" type="password" autoComplete={register ? "new-password" : "current-password"} value={password} required disabled={busy}
              aria-invalid={!!fieldError("password")} aria-describedby={`auth-password-help${fieldError("password") ? " auth-password-error" : ""}`}
              onBlur={() => setTouched(previous => ({ ...previous, password: true }))} onChange={e => edit("password", e.target.value)} />
            <p className="auth-muted" id="auth-password-help">10–128 characters, up to 512 UTF-8 bytes. Spaces and Unicode are kept exactly as entered.</p>
            {fieldError("password") && <p className="auth-field-error" id="auth-password-error" role="alert">{fieldError("password")}</p>}
          </div>
          <button className="auth-primary" disabled={busy || auth.loading}>{busy ? "Please wait…" : register ? "Register" : "Login"}</button>
          <button className="auth-text-button" type="button" disabled={busy} onClick={() => { setRegister(!register); setError(""); setPassword(""); setTouched({}); setServerErrors({}); }}>
            {register ? "Already have an account? Sign In" : "Create account"}</button>
          <p className="auth-muted auth-guest-note">You can also play as a guest. Guest games stay on this browser until you save them to an account.</p>
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
    <SectionHeader title="My Active Games" eyebrow="Saved to your account"><button className="btn subtle" disabled={loading} onClick={() => setRetry(n => n + 1)}>Check again</button></SectionHeader>
    {loading && <p>Checking games…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && !games.length && <EmptyState title="No account games yet">Host, Join or save a guest game to keep your seat with this account.</EmptyState>}
    <div className="recent-games-list">{games.map(game => <GameCard key={game.room_code} code={game.room_code} game={game} loading={loading}
      onContinue={() => auth.client.continueAccount(game.room_code, game.own_name)} />)}</div>
  </section>;
}
