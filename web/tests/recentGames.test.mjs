import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as runtime from "react/jsx-runtime";

const require = createRequire(import.meta.url);
let buttons = [];
const jsx = { ...runtime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (type === "button") buttons.push(props);
  return runtime[name](type, props, key);
}])) };
async function load(path) {
  const compiled = await build({ entryPoints: [fileURLToPath(new URL(path, import.meta.url))],
    bundle: true, write: false, format: "cjs", platform: "node", jsx: "automatic",
    define: { "import.meta.env": "{}" }, external: ["react", "react/jsx-runtime"], loader: { ".css": "empty" } });
  const module = { exports: {} };
  new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()
    (name => name === "react/jsx-runtime" ? jsx : require(name), module, module.exports);
  return module.exports;
}
const storage = await load("../src/recentGames.ts");
const { RecentGamesCards, discoverRecentGames } = await load("../src/components/RecentGames.tsx");
const { WSClient } = await load("../src/wsClient.ts");
function memoryStorage() {
  const values = new Map();
  return { get length() { return values.size; }, key: i => [...values.keys()][i] ?? null,
    getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
}
class Socket {
  static OPEN = 1;
  static latest;
  sent = []; readyState = 0;
  constructor() { Socket.latest = this; }
  open() { this.readyState = 1; this.onopen(); }
  send(raw) { this.sent.push(JSON.parse(raw)); }
  receive(message) { this.onmessage({ data: JSON.stringify(message) }); }
  close() { this.readyState = 3; this.onclose?.(); }
}
const binding = (code = "ABCDEF", token = "bearer-secret", name = "Cached Alice", seen = 100) => ({
  room_code: code, reconnect_token: token, last_known_name: name, last_seen_at: seen });
function available(entry, status = "active", name = "Server Alice") {
  return { status: "available", game: { room_code: entry.room_code, own_name: name, own_color: "white",
    map_name: "Base Standard", status, player_count: 2, max_players: 4, connected_count: 1,
    target_vp: 10, updated_at: "2026-10-06T00:00:00Z", can_continue: true,
    ...(status === "game_over" ? { winner: { name: "Bob", color: "blue" } } : {}) } };
}
beforeEach(() => {
  globalThis.localStorage = memoryStorage(); globalThis.sessionStorage = memoryStorage();
  globalThis.window = { setTimeout, clearTimeout }; globalThis.WebSocket = Socket;
  buttons = [];
});

test("empty storage has no cards or network request and preserves Create/Join availability", async () => {
  globalThis.fetch = () => { throw Error("must not fetch"); };
  assert.deepEqual(await discoverRecentGames(), []);
  assert.equal(renderToStaticMarkup(React.createElement(RecentGamesCards, { cards: [], loading: false, onContinue() {} })), '<div class="recent-games-list"></div>');
});
test("migration preserves legacy room/name proof, drops pid and removes legacy only after successful write", () => {
  localStorage.setItem("catan_reconnect_ABCDEF_Name_with_underscores", JSON.stringify({ token: "old-proof", pid: 5 }));
  localStorage.setItem("catan_reconnect_BROKEN_Name", "broken-json");
  const expected = binding("ABCDEF", "old-proof", "Name_with_underscores", 0);
  assert.deepEqual(storage.readRecentGames(), [expected]);
  assert.deepEqual(JSON.parse(localStorage.getItem(storage.RECENT_GAMES_KEY)), { version: 1, entries: [expected] });
  assert.equal(localStorage.getItem("catan_reconnect_ABCDEF_Name_with_underscores"), null);
  const failing = memoryStorage();
  failing.setItem("catan_reconnect_ABCDEF_Alice", '{"token":"preserved","pid":0}');
  failing.setItem = () => { throw Error("quota denied"); };
  assert.equal(storage.readRecentGames(failing)[0].reconnect_token, "preserved");
  assert.notEqual(failing.getItem("catan_reconnect_ABCDEF_Alice"), null);
});
test("bounded list retains newest ten distinct proofs, rematch changes no identity, future schemas survive", () => {
  for (let i = 0; i < 12; i++) storage.saveRecentGame(binding(`ROOM${i}`, `proof${i}`, "Alice", i));
  assert.equal(storage.readRecentGames().length, 10);
  assert.equal(storage.readRecentGames()[0].room_code, "ROOM11");
  storage.saveRecentGame(binding("ROOM11", "proof11", "New name", 1000));
  assert.equal(storage.readRecentGames().length, 10);
  assert.equal(storage.readRecentGames()[0].last_known_name, "New name");
  localStorage.setItem(storage.RECENT_GAMES_KEY, '{"version":99,"entries":["future-proof"]}');
  storage.saveRecentGame(binding());
  assert.equal(JSON.parse(localStorage.getItem(storage.RECENT_GAMES_KEY)).version, 99);
});
test("storage strips unnecessary fields instead of persisting a pid or private snapshot", () => {
  storage.saveRecentGame({ ...binding(), pid: 4, state: { private_hand: "must be discarded" } });
  assert.deepEqual(storage.readRecentGames(), [binding()]);
  assert(!localStorage.getItem(storage.RECENT_GAMES_KEY).includes("private_hand"));
});
test("bounded migration never deletes an overflow legacy proof without its replacement", () => {
  for (let i = 0; i < 11; i++) localStorage.setItem(`catan_reconnect_ROOM${i}_Alice`, JSON.stringify({ token: `proof${i}`, pid: 0 }));
  const entries = storage.readRecentGames();
  assert.equal(entries.length, 10);
  assert.equal(localStorage.getItem("catan_reconnect_ROOM10_Alice") !== null, true);
  storage.removeRecentGame(entries[0]);
  assert.equal(storage.readRecentGames().some(e => e.reconnect_token === "proof10"), true);
  assert.equal(localStorage.getItem("catan_reconnect_ROOM10_Alice"), null);
});
test("one request validates multiple games; server name/color replace cached display without token in markup", async () => {
  const entries = [binding(), binding("UVWXYZ", "other-proof", "Other cached", 90)];
  entries.forEach(storage.saveRecentGame);
  let requests = 0;
  globalThis.fetch = async (url, request) => {
    requests++;
    assert.equal(url, "/api/reconnect/inspect-many"); assert.equal(request.method, "POST");
    assert.equal(request.cache, "no-store");
    assert.deepEqual(JSON.parse(request.body).credentials, entries.map(({ room_code, reconnect_token }) => ({ room_code, reconnect_token })));
    return { ok: true, json: async () => ({ results: entries.map(e => available(e)) }) };
  };
  const cards = await discoverRecentGames();
  assert.equal(requests, 1); assert.equal(cards.length, 2);
  assert.equal(storage.readRecentGames()[0].last_known_name, "Server Alice");
  let continued;
  const html = renderToStaticMarkup(React.createElement(RecentGamesCards, { cards, loading: false, onContinue: entry => { continued = entry; } }));
  assert.match(html, /Base Standard/); assert.match(html, /Server Alice/); assert.match(html, /In Game/);
  assert.match(html, /2\/4 players/); assert(!html.includes("bearer-secret") && !html.includes("Cached Alice"));
  buttons[0].onClick();
  assert.deepEqual(continued, { ...entries[0], last_known_name: "Server Alice" });
});
test("confirmed invalid/closed removes only its binding and its current pointer", async () => {
  const bad = binding(), good = binding("UVWXYZ", "good-proof", "Bob", 90);
  storage.saveRecentGame(bad); storage.saveRecentGame(good); storage.setCurrentGame(bad);
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ results: [{ status: "invalid" }, available(good)] }) });
  const cards = await discoverRecentGames();
  assert.equal(cards.length, 1); assert.equal(cards[0].binding.room_code, "UVWXYZ");
  assert.equal(storage.readRecentGames().length, 1); assert.equal(storage.currentGame(), undefined);
});
for (const failure of [503, 429, "network", "malformed"]) {
  test(`temporary ${failure} retains every proof and current binding`, async () => {
    const entry = binding(); storage.saveRecentGame(entry); storage.setCurrentGame(entry);
    globalThis.fetch = async () => {
      if (failure === "network") throw Error("offline");
      return { ok: typeof failure === "string", status: failure, json: async () => ({ results: [] }) };
    };
    const cards = await discoverRecentGames();
    assert.equal(cards[0].inspection.status, "temporarily_unavailable");
    assert.deepEqual(storage.readRecentGames(), [entry]); assert.deepEqual(storage.currentGame(), entry);
    const html = renderToStaticMarkup(React.createElement(RecentGamesCards, { cards, loading: false, onContinue() {} }));
    assert.match(html, /Temporarily unavailable/); assert.equal(buttons[0].disabled, true);
  });
}
test("loading is local to cards; game-over returns to room and shows public winner", () => {
  const entry = binding(), cards = [{ binding: entry, inspection: available(entry, "game_over") }];
  let html = renderToStaticMarkup(React.createElement(RecentGamesCards, { cards, loading: true, onContinue() {} }));
  assert.match(html, /Checking/); assert.equal(buttons[0].disabled, true);
  buttons = [];
  html = renderToStaticMarkup(React.createElement(RecentGamesCards, { cards, loading: false, onContinue() {} }));
  assert.match(html, /Game Over/); assert.match(html, /Winner: Bob/); assert.match(html, /Return to Room/);
  assert.equal(buttons[0].disabled, false);
});
test("Continue and refresh use existing reconnect, server pid/name and one rematch-independent entry", () => {
  const entry = binding(); storage.saveRecentGame(entry); storage.setCurrentGame(entry);
  const client = new WSClient();
  client.restoreCurrentGame("ws://test/ws"); Socket.latest.open();
  assert.deepEqual(Socket.latest.sent.map(m => m.type), ["hello", "reconnect"]);
  assert.deepEqual(Socket.latest.sent[1], { type: "reconnect", room_code: "ABCDEF", reconnect_token: "bearer-secret" });
  Socket.latest.receive({ type: "room_state", room_code: "ABCDEF", map_revision: 1, status: "in_match",
    players: [{ pid: 2, name: "Server Alice" }] });
  Socket.latest.receive({ type: "reconnect_token", room_code: "ABCDEF", pid: 2, reconnect_token: "bearer-secret", match_id: 1, last_seq_applied: 7 });
  assert.equal(client.youPid, 2); assert.equal(client.seq, 7);
  Socket.latest.receive({ type: "room_state", room_code: "ABCDEF", map_revision: 1, status: "in_match", players: [{ pid: 0, name: "Server Alice" }] });
  Socket.latest.receive({ type: "reconnect_token", room_code: "ABCDEF", pid: 0, reconnect_token: "bearer-secret", match_id: 2, last_seq_applied: 0 });
  assert.equal(client.youPid, 0); assert.equal(client.seq, 0);
  assert.equal(storage.readRecentGames().length, 1);
  assert.deepEqual(Object.keys(storage.readRecentGames()[0]).sort(), ["last_known_name", "last_seen_at", "reconnect_token", "room_code", "server_url"]);
  assert.equal(storage.currentGame().last_known_name, "Server Alice");
  client.leaveRoom(); assert.equal(storage.currentGame(), undefined); assert.equal(storage.readRecentGames().length, 1);
});
test("lost storage never falls back to nickname recovery and invalid Continue does not loop", () => {
  const entry = binding(); storage.setCurrentGame(entry);
  const client = new WSClient(); let scheduled = false;
  window.setTimeout = () => { scheduled = true; return 1; };
  Socket.latest = undefined; client.restoreCurrentGame("ws://test/ws"); assert.equal(Socket.latest, undefined);
  storage.saveRecentGame(entry); client.continueGame(entry, "ws://test/ws"); Socket.latest.open();
  Socket.latest.receive({ type: "error", code: "forbidden", message: "Invalid credential" });
  Socket.latest.close();
  assert.equal(scheduled, false); assert.equal(storage.readRecentGames().length, 0);
  assert.equal(Socket.latest.sent.some(m => m.type === "join_room"), false);
});
test("stale nickname refresh republishes verified lobby identity and manual Host cancels an opening reconnect", () => {
  const entry = binding(); storage.saveRecentGame(entry); storage.setCurrentGame(entry);
  const client = new WSClient(), updates = [];
  client.onRoomState = () => updates.push(client.youPid);
  client.restoreCurrentGame("ws://test/ws"); Socket.latest.open();
  Socket.latest.receive({ type: "room_state", room_code: "ABCDEF", map_revision: 0, status: "lobby", host_pid: 1,
    players: [{ pid: 1, name: "Server Alice" }] });
  assert.equal(updates.at(-1), null);
  Socket.latest.receive({ type: "reconnect_token", room_code: "ABCDEF", pid: 1, reconnect_token: "bearer-secret", match_id: 0, last_seq_applied: 0 });
  assert.equal(updates.at(-1), 1); assert.equal(storage.currentGame().last_known_name, "Server Alice");
  client.leaveRoom(); client.continueGame(entry, "ws://test/ws");
  const old = Socket.latest;
  client.host(2); client.connect("ws://test/ws", "New Host");
  assert.equal(old.onopen, null); assert.equal(old.onmessage, null);
  Socket.latest.open(); assert.equal(Socket.latest.sent.at(-1).type, "create_room");
  assert.equal(storage.currentGame(), undefined);
});
test("a late aborted inspection cannot remove proof or resurrect a departed room", async () => {
  const entry = binding(); storage.saveRecentGame(entry);
  const abort = new AbortController();
  globalThis.fetch = async () => { abort.abort(); return { ok: true, json: async () => ({ results: [{ status: "invalid" }] }) }; };
  await discoverRecentGames(abort.signal);
  assert.deepEqual(storage.readRecentGames(), [entry]);
});
test("manual-server proof is retained, never inspected against another backend, and refresh uses its URL", async () => {
  const remote = { ...binding(), server_url: "ws://other-server/ws" };
  storage.saveRecentGame(remote); storage.setCurrentGame(remote);
  globalThis.fetch = () => { throw Error("a foreign proof must not be sent here"); };
  assert.deepEqual(await discoverRecentGames(undefined, "ws://default-server/ws"), []);
  assert.deepEqual(storage.readRecentGames(), [remote]);
  const client = new WSClient();
  client.restoreCurrentGame("ws://default-server/ws"); Socket.latest.open();
  assert.equal(client.isOpen("ws://other-server/ws"), true);
  assert.equal(client.isOpen("ws://default-server/ws"), false);
  client.loadToken("ABCDEF", "Cached Alice", "ws://default-server/ws");
  client.connect("ws://default-server/ws", "Cached Alice"); client.join("ABCDEF"); Socket.latest.open();
  assert.equal(Socket.latest.sent.at(-1).type, "join_room");
});
test("changing server clears old revisions and pending commands even if room code and epoch collide", () => {
  const client = new WSClient();
  client.connect("ws://first/ws", "Alice"); Socket.latest.open();
  Socket.latest.receive({ type: "room_state", room_code: "ABCDEF", status: "in_match", config_revision: 9, map_revision: 9, players: [{ pid: 0, name: "Alice" }] });
  Socket.latest.receive({ type: "reconnect_token", room_code: "ABCDEF", pid: 0, reconnect_token: "first-proof", match_id: 1, last_seq_applied: 7 });
  client.sendCmd({ type: "roll" });
  storage.saveRecentGame({ ...binding("ABCDEF", "second-proof", "Alice"), server_url: "ws://second/ws" });
  client.loadToken("ABCDEF", "Alice", "ws://second/ws");
  client.connect("ws://second/ws", "Alice"); client.join("ABCDEF"); Socket.latest.open();
  Socket.latest.receive({ type: "room_state", room_code: "ABCDEF", status: "in_match", config_revision: 0, map_revision: 0, players: [{ pid: 1, name: "Alice" }] });
  Socket.latest.receive({ type: "reconnect_token", room_code: "ABCDEF", pid: 1, reconnect_token: "second-proof", match_id: 1, last_seq_applied: 0 });
  assert.equal(client.roomState.map_revision, 0); assert.equal(client.seq, 0); assert.equal(client.youPid, 1);
  assert.equal(Socket.latest.sent.some(m => m.type === "cmd"), false);
  assert.equal(Socket.latest.sent.at(-1).reconnect_token, "second-proof");
});
for (const intent of ["host", "join"]) test(`manual ${intent} fences replies from an unfinished automatic reconnect`, () => {
  const oldEntry = binding(); storage.saveRecentGame(oldEntry); storage.setCurrentGame(oldEntry);
  const other = binding("UVWXYZ", "other-proof", "Alice"); storage.saveRecentGame(other);
  const client = new WSClient(); client.restoreCurrentGame("ws://test/ws"); Socket.latest.open();
  const old = Socket.latest;
  if (intent === "host") client.host(2);
  else { client.loadToken("UVWXYZ", "Alice", "ws://test/ws"); client.connect("ws://test/ws", "Alice"); client.join("UVWXYZ"); }
  assert.equal(old.onmessage, null); assert.equal(old.onclose, null);
  Socket.latest.open();
  assert.equal(Socket.latest.sent.at(-1).type, intent === "host" ? "create_room" : "reconnect");
  assert.equal(storage.readRecentGames().some(e => e.reconnect_token === oldEntry.reconnect_token), true);
  assert.equal(storage.readRecentGames().some(e => e.reconnect_token === other.reconnect_token), true);
});
