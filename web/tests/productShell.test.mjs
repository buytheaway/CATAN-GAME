import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";

const require = createRequire(import.meta.url);
const compiled = await build({
  stdin: { contents: `export * from "./shell/PageShell"; export * from "./auth/validation";
    export { default as LobbyPage } from "./components/LobbyPage";
    export { default as GameCard } from "./shell/GameCard";`,
    resolveDir: fileURLToPath(new URL("../src", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  external: ["react", "react/jsx-runtime"], loader: { ".css": "empty" }, define: { "import.meta.env": "{}" },
});
let elements = [];
const runtime = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (typeof type === "string") elements.push({ type, ...props });
  return jsxRuntime[name](type, props, key);
}])) };
const loaded = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  name => name === "react/jsx-runtime" ? runtime : require(name), loaded, loaded.exports);
const { validateAuth, authErrorField, LobbyPage, GameCard, PageShell } = loaded.exports;
const fields = { username: "Captain_3", display_name: "Капитан 🌊", password: "  open water 🌊  " };
const check = (patch, register = true) => validateAuth({ ...fields, ...patch }, register);
function render(component, props) {
  elements = [];
  return { html: renderToStaticMarkup(React.createElement(component, props)), elements };
}

test("username sign-in accepts ASCII names case-insensitively and rejects email/Cyrillic/control input", () => {
  assert.deepEqual(check({ username: "  CaPtAiN-3  " }), {});
  for (const username of ["captain@example.com", "Капитан", "ab", "a".repeat(33), "abc\n", "abc\u200d"])
    assert.match(check({ username }).username, /ASCII|Email/);
  assert.equal(fields.password, "  open water 🌊  ");
});

test("display name is separate from login, allows Unicode and uses code-point length", () => {
  assert.deepEqual(check({ display_name: "🌊".repeat(32) }), {});
  for (const display_name of ["   ", "🌊".repeat(33), "Captain\t", "Captain\ue000", "Captain\u200d"])
    assert.match(check({ display_name }).display_name, /1–32/);
  assert.deepEqual(check({ display_name: "" }, false), {});
});

test("password uses Python code-point boundaries, preserves spaces and rejects unencodable surrogates", () => {
  assert.match(check({ password: "🌊".repeat(9) }).password, /10–128/);
  assert.deepEqual(check({ password: "🌊".repeat(10) }), {});
  assert.deepEqual(check({ password: "🌊".repeat(128) }), {}); // exactly 512 UTF-8 bytes
  assert.match(check({ password: "🌊".repeat(129) }).password, /512/);
  assert.match(check({ password: "abcdefghi\ud800" }).password, /10–128/);
  assert.deepEqual(check({ password: "          " }), {}); // backend intentionally has no composition/trim rule
});

test("known field errors stay attached to their field; credentials/origin/session errors stay at form level", () => {
  assert.equal(authErrorField("username_taken"), "username");
  assert.equal(authErrorField("invalid_username"), "username");
  assert.equal(authErrorField("invalid_display_name"), "display_name");
  assert.equal(authErrorField("invalid_password"), "password");
  for (const code of ["invalid_credentials", "origin_forbidden", "session_expired", "rate_limited", "persistence_unavailable"])
    assert.equal(authErrorField(code), undefined);
});

const room = { room_code: "ROOM01", status: "lobby", host_pid: 0, max_players: 4,
  map_id: "base_standard", map_revision: 1, map_rules: { target_vp: 10, robber_count: 1 }, settings: { target_vp: 12 },
  players: [{ pid: 0, name: "Captain", connected: true, color: "red" }, { pid: 1, name: "Navigator", connected: true, color: "blue" },
    { pid: 2, name: null, connected: false }, { pid: 3, name: null, connected: false }] };
function lobby(overrides = {}, clientPatch = {}, status = "connected") {
  return render(LobbyPage, { room: { ...room, ...overrides }, client: { youPid: 0, pendingMapId: null, ...clientPatch },
    status, wsDefault: "ws://test/ws", error: null });
}

test("home exposes separate Host/Join forms and the existing Host connection intent", () => {
  const calls = [];
  const client = { pendingMapId: null, setName: value => calls.push(["name", value]), isOpen: () => false,
    connect: (...args) => calls.push(["connect", ...args]), host: value => calls.push(["host", value]) };
  const view = render(LobbyPage, { room: null, client, status: "idle", wsDefault: "ws://test/ws", error: null });
  const forms = view.elements.filter(e => e.type === "form");
  assert.deepEqual(forms.map(e => e["aria-label"]), ["Host game", "Join room"]);
  forms[0].onSubmit({ preventDefault() {} });
  assert.deepEqual(calls, [["name", "Player"], ["connect", "ws://test/ws", "Player"], ["host", 4]]);
  for (const pattern of [/Advanced connection/, /No saved tables yet/, /Guest games are recoverable/]) assert.match(view.html, pattern);
  assert.match(view.html, /Choose the map, custom JSON and match rules in your room/);
});

test("room presents real occupied/open seats and confirmed target override without sending any intents", () => {
  const view = lobby();
  assert.equal(view.elements.find(e => e.type === "button" && e.children === "Start Match").disabled, false);
  assert.match(view.html, /Target VP 12/);
  assert.equal((view.html.match(/Open seat/g) ?? []).length, 2);
  for (const pattern of [/Online/, /Host/, /Room chat/]) assert.match(view.html, pattern);
});

test("Start and map editing preserve host/connection/lifecycle/pending/participant guards", () => {
  const cases = [
    { client: { youPid: 1 }, mapDisabled: true },
    { status: "reconnecting", mapDisabled: true },
    { room: { status: "in_match" }, mapDisabled: true },
    { room: { players: room.players.map(p => p.pid === 1 ? { ...p, connected: false } : p) }, mapDisabled: false },
    { client: { pendingMapId: "seafarers_gold_haven" }, mapDisabled: false },
    { client: { configPending: true }, mapDisabled: false },
  ];
  for (const entry of cases) {
    const view = lobby(entry.room, entry.client, entry.status);
    assert.equal(view.elements.find(e => e.type === "button" && e.children === "Start Match").disabled, true);
    assert.equal(view.elements.find(e => e.type === "select" && e["aria-label"] === "Map preset").disabled, entry.mapDisabled);
  }
});

test("a public game card renders map/identity/color/presence and invokes the caller's Continue", () => {
  const game = { room_code: "ROOM01", map_name: "Gold Haven", own_name: "Капитан <3", own_color: "white",
    player_count: 2, max_players: 4, connected_count: 1, status: "active", can_continue: true };
  let continued = 0;
  const view = render(GameCard, { code: game.room_code, game, loading: false, onContinue: () => continued++ });
  for (const pattern of [/Gold Haven/, /Капитан &lt;3/, /2\/4 players/, /1 online/, /#f2f4f8/]) assert.match(view.html, pattern);
  const button = view.elements.find(e => e.type === "button" && e.children === "Continue");
  assert.equal(button.disabled, false); button.onClick(); assert.equal(continued, 1);
});

test("shell uses the exact product identity and accessible connection/account affordances", () => {
  const view = render(PageShell, { status: "reconnecting", account: React.createElement("button", null, "Sign In"), children: "Home" });
  for (const pattern of [/Danik Inc\. Entertainment/, /CATAN.КОЛОНИЗАТОРЫ/, /Reconnecting…/, /<main/, /role="status"/]) assert.match(view.html, pattern);
  assert.doesNotMatch(view.html, /<canvas/);
});
