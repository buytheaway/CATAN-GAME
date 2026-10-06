/** Guest proofs only: no pid, match epoch, snapshot or private gameplay cache. */
export const RECENT_GAMES_KEY = "catan_recent_games";
export const CURRENT_GAME_KEY = "catan_current_game";
export const MAX_RECENT_GAMES = 10;
export type RecentGame = {
  room_code: string; reconnect_token: string; last_known_name: string; last_seen_at: number;
  server_url?: string;
};
export type GameSummary = {
  room_code: string; map_name: string; own_name: string; own_color: string;
  player_count: number; max_players: number; connected_count: number;
  status: "lobby" | "active" | "game_over"; target_vp: number;
  updated_at: string; can_continue: boolean;
  winner?: { name: string; color: string };
};
export type Inspection = { status: "available"; game: GameSummary }
  | { status: "invalid" | "temporarily_unavailable" };

function local(): Storage | undefined {
  try { return globalThis.localStorage; } catch { return undefined; }
}
function session(): Storage | undefined {
  try { return globalThis.sessionStorage; } catch { return undefined; }
}
function isEntry(value: any): value is RecentGame {
  return value && typeof value.room_code === "string" && /^[A-Z0-9]{1,32}$/.test(value.room_code)
    && typeof value.reconnect_token === "string" && value.reconnect_token.length > 0 && value.reconnect_token.length <= 512
    && typeof value.last_known_name === "string" && value.last_known_name.length <= 128
    && (value.server_url === undefined || typeof value.server_url === "string" && /^wss?:\/\//.test(value.server_url) && value.server_url.length <= 2048)
    && typeof value.last_seen_at === "number" && Number.isFinite(value.last_seen_at) && value.last_seen_at >= 0;
}
export function sameBinding(a: RecentGame, b: RecentGame) {
  return a.room_code === b.room_code && a.reconnect_token === b.reconnect_token
    && (!a.server_url || !b.server_url || a.server_url === b.server_url);
}
function bounded(entries: RecentGame[]) {
  return entries.filter(isEntry).sort((a, b) => b.last_seen_at - a.last_seen_at)
    .filter((entry, i, all) => all.findIndex(other => sameBinding(entry, other)) === i).slice(0, MAX_RECENT_GAMES)
    .map(({ room_code, reconnect_token, last_known_name, last_seen_at, server_url }) => ({ room_code, reconnect_token, last_known_name, last_seen_at,
      ...(server_url ? { server_url } : {}) }));
}
function write(entries: RecentGame[], storage = local()): boolean {
  try {
    if (!storage) return false;
    const current = JSON.parse(storage.getItem(RECENT_GAMES_KEY) ?? "null");
    if (current && current.version !== 1) return false;
    storage.setItem(RECENT_GAMES_KEY, JSON.stringify({ version: 1, entries: bounded(entries) }));
    return true;
  } catch { return false; }
}
export function readRecentGames(storage = local()): RecentGame[] {
  if (!storage) return [];
  try {
    const current = JSON.parse(storage.getItem(RECENT_GAMES_KEY) ?? "null");
    if (current && current.version !== 1) return [];
    const entries: RecentGame[] = Array.isArray(current?.entries) ? current.entries.filter(isEntry) : [];
    const legacy: { key: string; entry: RecentGame }[] = [];
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i)!;
      const match = /^catan_reconnect_([A-Z0-9]{1,32})_(.+)$/.exec(key);
      if (!match) continue;
      try {
        const value = JSON.parse(storage.getItem(key)!);
        const entry = { room_code: match[1], reconnect_token: value.token, last_known_name: match[2], last_seen_at: 0 };
        if (isEntry(entry)) { entries.push(entry); legacy.push({ key, entry }); }
      } catch { /* A damaged legacy entry must not hide other usable proofs. */ }
    }
    const result = bounded(entries);
    if (legacy.length && write(result, storage)) legacy.forEach(({ key, entry }) => {
      if (result.some(saved => sameBinding(saved, entry))) storage.removeItem(key);
    }); // Overflow legacy proofs stay intact until a bounded slot can hold them.
    return result;
  } catch { return []; }
}
export function saveRecentGame(entry: RecentGame) {
  if (isEntry(entry)) write([entry, ...readRecentGames().filter(old => !sameBinding(old, entry))]);
}
export function recentGamesForServer(url: string) {
  return readRecentGames().filter(entry => !entry.server_url || entry.server_url === url);
}
export function removeRecentGame(entry: RecentGame) {
  write(readRecentGames().filter(old => !sameBinding(old, entry)));
  if (sameCurrent(entry)) clearCurrentGame();
}
export function updateRecentName(entry: RecentGame, name: string) {
  const existing = readRecentGames().find(old => sameBinding(old, entry));
  if (!existing) return; // A late HTTP response must not resurrect a removed binding.
  const active = sameCurrent(existing);
  saveRecentGame({ ...existing, last_known_name: name });
  if (active) setCurrentGame({ ...existing, last_known_name: name });
}
function sameCurrent(entry: RecentGame) {
  try {
    const value = JSON.parse(session()?.getItem(CURRENT_GAME_KEY) ?? "null");
    return value?.room_code === entry.room_code && value?.last_known_name === entry.last_known_name
      && value?.server_url === entry.server_url;
  } catch { return false; }
}
export function setCurrentGame(entry: RecentGame) {
  try { session()?.setItem(CURRENT_GAME_KEY, JSON.stringify({ room_code: entry.room_code, last_known_name: entry.last_known_name,
    ...(entry.server_url ? { server_url: entry.server_url } : {}) })); }
  catch { /* Manual Continue works without sessionStorage. */ }
}
export function clearCurrentGame() {
  try { session()?.removeItem(CURRENT_GAME_KEY); } catch { /* Best effort. */ }
}
export function currentGame(): RecentGame | undefined {
  try {
    const value = JSON.parse(session()?.getItem(CURRENT_GAME_KEY) ?? "null");
    return readRecentGames().find(entry => entry.room_code === value?.room_code && entry.last_known_name === value?.last_known_name
      && entry.server_url === value?.server_url);
  } catch { return undefined; }
}
export async function inspectRecentGames(entries: RecentGame[], signal?: AbortSignal): Promise<Inspection[]> {
  const response = await fetch("/api/reconnect/inspect-many", {
    method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store", signal,
    body: JSON.stringify({ credentials: entries.map(entry => ({ room_code: entry.room_code, reconnect_token: entry.reconnect_token })) }),
  });
  if (!response.ok) throw new Error("Recent games temporarily unavailable");
  const body = await response.json();
  if (!Array.isArray(body.results) || body.results.length !== entries.length) throw new Error("Invalid inspection response");
  return body.results.map((result: any, i: number) => {
    if (result.status === "invalid" || result.status === "temporarily_unavailable") return { status: result.status };
    const game = result.game;
    if (result.status !== "available" || !game || game.room_code !== entries[i].room_code
        || typeof game.own_name !== "string" || typeof game.map_name !== "string"
        || !["lobby", "active", "game_over"].includes(game.status)) throw new Error("Invalid inspection response");
    return { status: "available", game };
  });
}
