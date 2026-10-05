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
let select, start;
const tracedRuntime = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (type === "select" && props["aria-label"] === "Map preset") select = props;
  if (type === "button" && props.children === "Start Match") start = props;
  return jsxRuntime[name](type, props, key);
}])) };
const loaded = { exports: {} };
new Script(`(function(require, module, exports) { ${compiled.outputFiles[0].text}\n})`)
  .runInThisContext()(name => name === "react/jsx-runtime" ? tracedRuntime : require(name), loaded, loaded.exports);
const LobbyPage = loaded.exports.default;

function render(pendingMapId = null, mapId = "base_standard") {
  const sent = [];
  const client = { pendingMapId, youPid: 0, setMap: id => sent.push(id) };
  const room = { room_code: "ROOM", map_revision: 1, map_id: mapId, host_pid: 0,
    status: "lobby", max_players: 2,
    players: [{ pid: 0, name: "Alice", connected: true }, { pid: 1, name: "Bob", connected: true }],
    map_presets: [{ id: "base_standard", name: "Base" }, { id: "seafarers_gold_haven", name: "Gold Haven" }] };
  const html = renderToStaticMarkup(React.createElement(LobbyPage, {
    client, room, status: "connected", wsDefault: "ws://test/ws", error: null,
  }));
  return { sent, html, select, start };
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
