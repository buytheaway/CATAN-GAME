import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";

// Same in-memory TSX/real React rendering approach as BoardView.test.mjs.
const require = createRequire(import.meta.url);
const compiled = await build({
  entryPoints: [fileURLToPath(new URL("../src/components/LobbyPage.tsx", import.meta.url))],
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  external: ["react", "react/jsx-runtime"],
  loader: { ".css": "empty" },
});
let select, start, close;
const tracedRuntime = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (type === "select" && props["aria-label"] === "Map preset") select = props;
  if (type === "button" && props.children === "Start Match") start = props;
  if (type === "button" && ["Close Lobby", "Closing lobby…"].includes(props.children)) close = props;
  return jsxRuntime[name](type, props, key);
}])) };
const loaded = { exports: {} };
new Script(`(function(require, module, exports) { ${compiled.outputFiles[0].text}\n})`)
  .runInThisContext()(name => name === "react/jsx-runtime" ? tracedRuntime : require(name), loaded, loaded.exports);
const LobbyPage = loaded.exports.default;

function render(pendingMapId = null, mapId = "base_standard", options = {}) {
  const sent = [];
  close = null;
  const client = { pendingMapId, youPid: 0, setMap: id => sent.push(id), closeLobby: () => sent.push("close"), ...options.client };
  const room = options.room === null ? null : { room_code: "ROOM", map_revision: 1, map_id: mapId, host_pid: 0,
    status: "lobby", max_players: 2,
    players: [{ pid: 0, name: "Alice", connected: true }, { pid: 1, name: "Bob", connected: true }],
    map_presets: [{ id: "base_standard", name: "Base" }, { id: "seafarers_gold_haven", name: "Gold Haven" }], ...options.room };
  const html = renderToStaticMarkup(React.createElement(LobbyPage, {
    client, room, status: options.status ?? "connected", wsDefault: "ws://test/ws", error: null, closedLobby: options.closedLobby,
  }));
  return { sent, html, select, start, close };
}

test("lobby selection handler sends the user's preset directly", () => {
  const view = render();
  view.select.onChange({ target: { value: "seafarers_gold_haven" } });
  assert.deepEqual(view.sent, ["seafarers_gold_haven"]);
});

test("lobby shows the latest pending preset and disables Start until confirmation", () => {
  const pending = render("seafarers_gold_haven");
  assert.equal(pending.select.value, "seafarers_gold_haven");
  assert.equal(pending.start.disabled, true);
  const confirmed = render(null, "seafarers_gold_haven");
  assert.equal(confirmed.select.value, "seafarers_gold_haven");
  assert.equal(confirmed.start.disabled, false);
  assert.deepEqual(confirmed.sent, []);
});

test("custom JSON map IDs get a visible select option instead of an unrelated preset", () => {
  const view = render(null, "Custom Test Map");
  assert.equal(view.select.value, "Custom Test Map");
  assert.match(view.html, /<option value="Custom Test Map" selected="">Custom Test Map<\/option>/);
});

test("official New Shores layouts require their exact connected player count", () => {
  for (const required of [3, 4]) {
    const id = `seafarers_official_new_shores_${required}`;
    for (const online of [2, 3, 4]) {
      const players = Array.from({ length: 4 }, (_, pid) => ({ pid, name: `Player ${pid}`, connected: pid < online }));
      const view = render(null, id, { room: { max_players: 4, players,
        map_meta: { official_scenario: "heading_for_new_shores", required_players: required }, map_rules: { target_vp: 14 },
        map_presets: [{ id, name: `Heading for New Shores (${required} players)` }] } });
      assert.equal(view.start.disabled, online !== required, `${required}-player layout with ${online} online`);
      assert.match(view.html, new RegExp(`exactly ${required} connected players \\(${online} currently online\\)`));
      assert.match(view.html, /Fifth Edition \(2021\)/);
      assert.match(view.html, /Goal: 14 VP/);
      view.select.onChange({ target: { value: id } });
      assert.deepEqual(view.sent, [id]);
    }
  }
});

test("official Start still waits for configuration confirmation and host ownership", () => {
  const id = "seafarers_official_new_shores_3";
  const room = { map_meta: { official_scenario: "heading_for_new_shores", required_players: 3 }, map_rules: { target_vp: 14 },
    players: Array.from({ length: 3 }, (_, pid) => ({ pid, name: `Player ${pid}`, connected: true })) };
  assert.equal(render(id, id, { room }).start.disabled, true);
  assert.equal(render(null, id, { room, client: { configPending: true } }).start.disabled, true);
  assert.equal(render(null, id, { room, client: { youPid: 1 } }).start.disabled, true);
  assert.equal(render(null, id, { room, status: "disconnected" }).start.disabled, true);
  assert.equal(render(null, id, { room }).start.disabled, false);
});

test("Four Islands explains personal home islands and fixes the correct 13 VP variant", () => {
  for (const required of [3, 4]) {
    const id = `seafarers_official_four_islands_${required}`;
    for (const online of [2, 3, 4, 5]) {
      const view = render(null, id, { room: { max_players: 6,
        players: Array.from({ length: online }, (_, pid) => ({ pid, name: `Player ${pid}`, connected: true })),
        map_meta: { official_scenario: "the_four_islands", required_players: required }, map_rules: { target_vp: 13 },
        map_presets: [{ id, name: `The Four Islands (${required} players)` }] } });
      assert.equal(view.start.disabled, online !== required);
      assert.match(view.html, /Start on one or two islands of your choice/);
      assert.match(view.html, /first settlement on each foreign island earns 2 special VP/);
      assert.match(view.html, /Goal: 13 VP/);
      assert.doesNotMatch(view.html, /belong on the main island/);
      assert.equal(view.select.value, id);
    }
  }
});

test("Close Lobby is host-only, disabled offline/pending, and requires explicit confirmation", () => {
  const previousWindow = globalThis.window;
  try {
    const prompts = [];
    globalThis.window = { confirm: text => { prompts.push(text); return false; } };
    const host = render();
    assert.equal(host.close.disabled, false);
    host.close.onClick();
    assert.deepEqual(host.sent, []);
    assert.match(prompts[0], /Close lobby ROOM/);
    assert.match(prompts[0], /cannot be reconnected/);
    window.confirm = () => true;
    host.close.onClick();
    assert.deepEqual(host.sent, ["close"]);
    assert.match(host.html, /only disconnects you/);
    assert.equal(render(null, "base_standard", { client: { youPid: 1 } }).close, null);
    assert.equal(render(null, "base_standard", { room: { status: "in_match" } }).close, null);
    assert.equal(render(null, "base_standard", { status: "disconnected" }).close.disabled, true);
    assert.equal(render(null, "base_standard", { client: { closingLobby: true } }).close.disabled, true);
  } finally { globalThis.window = previousWindow; }
});

test("closed lobby shows a Home notice and has no gameplay or lobby controls", () => {
  const view = render(null, "base_standard", { room: null, closedLobby: "ROOM" });
  assert.match(view.html, /Lobby ROOM was closed by its host/);
  assert.match(view.html, /Reconnect is no longer available/);
  assert.doesNotMatch(view.html, />Start Match<|>Close Lobby<|aria-label="Room configuration"/);
  assert.match(view.html, /Host a game|Join a room/);
});
