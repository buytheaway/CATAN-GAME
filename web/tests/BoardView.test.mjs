import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";

// Render with real React hooks; capture DOM handlers since SSR does not attach them.
// The existing Vite dependency bundles TSX in memory; no files or dependencies added.
const require = createRequire(import.meta.url);
const compiled = await build({
  stdin: { contents: 'export {default as BoardView} from "./components/BoardView"; export {default as BoardControls} from "./board/BoardControls"; export {createBoardInteraction,emptySelection} from "./board/interaction";',
    resolveDir: fileURLToPath(new URL("../src/", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  external: ["react", "react/jsx-runtime"],
});
let clicks = [];
const tracedRuntime = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (type === "polygon" && props.onClick) clicks.push(props.onClick);
  return jsxRuntime[name](type, props, key);
}])) };
const loaded = { exports: {} };
new Script(`(function(require, module, exports) { ${compiled.outputFiles[0].text}\n})`)
  .runInThisContext()(name => name === "react/jsx-runtime" ? tracedRuntime : require(name), loaded, loaded.exports);
const { BoardView, BoardControls, createBoardInteraction, emptySelection } = loaded.exports;

function render(overrides = {}) {
  clicks = [];
  const sent = [];
  const state = {
    tiles: [
      { terrain: "desert", center: [0, 0] },
      { terrain: "forest", center: [100, 0] },
      { terrain: "sea", center: [200, 0] },
      { terrain: "sea", center: [300, 0] },
    ],
    size: 58, vertices: {}, edges: [], occupied_e: {}, occupied_ships: {}, occupied_v: {},
    edge_adj_hexes: {}, robber_tile: 0, pirate_tile: 2,
    pending_action: "robber_move", pending_pid: 0, turn: 0, phase: "main",
    rules_config: { enable_seafarers: true, enable_pirate: true }, ...overrides,
  };
  state.legal = { pid: 0, settlements: [], roads: [], cities: [], ships: [],
    robber_tiles: state.pending_action === "robber_move" && state.pending_pid === 0 ? [1] : [],
    pirate_tiles: state.pending_action === "robber_move" && state.pending_pid === 0 && state.rules_config.enable_pirate ? [3] : [],
    robber_victims: {}, pirate_victims: {} };
  const interaction = createBoardInteraction(state, 0, emptySelection(), () => {}, cmd => sent.push(cmd));
  const html = renderToStaticMarkup(React.createElement(React.Fragment, null,
    React.createElement(BoardView, { state, interaction }),
    React.createElement(BoardControls, { state, interaction })));
  assert.equal(clicks.length, 4);
  return { sent, html, click: tile => clicks[tile]() };
}

test("pending event lets map clicks choose pirate on sea and robber on land", () => {
  const { click, sent, html } = render();
  click(3);
  click(1);
  assert.deepEqual(sent, [{ type: "move_pirate", tile: 3 }, { type: "move_robber", tile: 1 }]);
  assert.match(html, /Click land for robber or sea for pirate/);
});

test("current robber and pirate tiles do not send a move", () => {
  const { click, sent } = render();
  click(0);
  click(2);
  assert.deepEqual(sent, []);
});

test("completed event hides pirate and map clicks send no commands", () => {
  const { click, sent, html } = render({ pending_action: null, pending_pid: null });
  click(1);
  click(3);
  assert.deepEqual(sent, []);
  assert.doesNotMatch(html, />Pirate<\/span>/);
});

test("another player's pending event does not authorize local map clicks", () => {
  const { click, sent } = render({ pending_pid: 1 });
  click(1);
  click(3);
  assert.deepEqual(sent, []);
});

test("scenario without pirate allows robber only", () => {
  const { click, sent, html } = render({ rules_config: { enable_seafarers: true, enable_pirate: false } });
  click(3);
  click(1);
  assert.deepEqual(sent, [{ type: "move_robber", tile: 1 }]);
  assert.doesNotMatch(html, />Pirate<\/span>/);
});
