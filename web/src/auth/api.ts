import { CURRENT_GAME_KEY } from "../recentGames";
import type { GameSummary } from "../recentGames";

export type User = { username: string; display_name: string };
export class AuthFailure extends Error {
  constructor(public code: string) { super(code); }
}
export const errorText: Record<string, string> = {
  invalid_credentials: "Username or password is incorrect.", username_taken: "This username is taken.",
  invalid_username: "Username must use 3–32 ASCII letters (A–Z), digits, underscores or dashes. Email and display names cannot be used to sign in.",
  invalid_display_name: "Display name must contain 1–32 visible characters.",
  invalid_password: "Password must contain 10–128 characters (up to 512 UTF-8 bytes).",
  unauthenticated: "Sign in to continue.", session_expired: "Your session expired. Sign in again.",
  seat_not_owned: "This game does not belong to this account.", guest_credential_invalid: "This guest place can no longer be claimed.",
  duplicate_room_membership: "You already own a seat in this room.", rate_limited: "Too many attempts. Try again shortly.",
  already_claimed: "This guest place already belongs to an account.",
  origin_forbidden: "Authentication is unavailable on this address. Check the server's allowed origins.",
  persistence_unavailable: "The server is temporarily unavailable. Your saved games are kept.",
};
export async function authRequest<T>(path: string, data?: unknown): Promise<T> {
  let response: Response;
  let body: any;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    response = await fetch(path, { method: data === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store", signal: controller.signal,
      headers: data === undefined ? undefined : { "Content-Type": "application/json" },
      body: data === undefined ? undefined : JSON.stringify(data) });
    body = await response.json();
  } catch { throw new AuthFailure("persistence_unavailable"); }
  finally { clearTimeout(timeout); }
  if (!response.ok) throw new AuthFailure(typeof body.error === "string" && body.error in errorText ? body.error : "persistence_unavailable");
  return body as T;
}
export async function getMe() {
  const me = await authRequest<{authenticated: boolean; user?: User}>("/api/auth/me");
  if (typeof me.authenticated !== "boolean" || me.authenticated && (!me.user || typeof me.user.username !== "string" || typeof me.user.display_name !== "string"))
    throw new AuthFailure("persistence_unavailable");
  return me;
}
export async function getActiveGames() {
  const result = await authRequest<{games: GameSummary[]}>("/api/games/active");
  if (!Array.isArray(result.games) || result.games.length > 50 || result.games.some(game => !game || typeof game.room_code !== "string" || typeof game.own_name !== "string"))
    throw new AuthFailure("persistence_unavailable");
  return result;
}
export function setAccountCurrent(room_code: string, server_url: string) {
  try { sessionStorage.setItem(CURRENT_GAME_KEY, JSON.stringify({ ownership: "account", room_code, server_url })); } catch { /* Continue is still usable. */ }
}
export function accountCurrent(): { room_code: string; server_url: string } | null {
  try {
    const entry = JSON.parse(sessionStorage.getItem(CURRENT_GAME_KEY) ?? "null");
    return entry?.ownership === "account" && typeof entry.room_code === "string" && typeof entry.server_url === "string" ? entry : null;
  } catch { return null; }
}
