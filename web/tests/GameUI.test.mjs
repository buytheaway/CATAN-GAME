import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";

// Real React SSR + captured DOM callbacks, as in BoardView tests. WebGL is covered in Chrome.
const require = createRequire(import.meta.url);
const compiled = await build({
  stdin: { contents: `export {default as GamePage} from "./components/GamePage";
    export {default as GameOverlay} from "./game/GameOverlay";
    export * from "./game/GameHUD"; export * from "./game/presentation";
    export {createBoardInteraction,emptySelection} from "./board/interaction";`,
    resolveDir: fileURLToPath(new URL("../src/", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  external: ["react", "react/jsx-runtime"], loader: { ".css": "empty" },
  plugins: [{ name: "no-webgl-in-ssr", setup(builder) {
    builder.onLoad({ filter: /board3d[\\/]Board3D\.tsx$/ }, () => ({
      contents: 'export default function Board3D(){return null}', loader: "tsx",
    }));
  } }],
});
let buttons;
const textOf = value => typeof value === "string" ? value : Array.isArray(value)
  ? value.map(textOf).join("") : value?.props ? textOf(value.props.children) : "";
const tracedRuntime = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (type === "button") buttons.push({ name: props["aria-label"] || textOf(props.children), ...props });
  return jsxRuntime[name](type, props, key);
}])) };
const loaded = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  name => name === "react/jsx-runtime" ? tracedRuntime : require(name), loaded, loaded.exports);
const { GamePage, GameOverlay, GameTopBar, ResourceHand, turnActions, buildTools,
  contextPrompt, createBoardInteraction, emptySelection } = loaded.exports;

function snapshot(overrides = {}) {
  return { size: 58, tiles: [], vertices: {}, edges: [], occupied_e: {}, occupied_ships: {}, occupied_v: {},
    phase: "main", turn: 0, rolled: false, pending_action: null, discard_required: {}, pending_gold: {},
    players: [{ pid: 0, name: "Alice", vp: 3, resource_count: 7, dev_count: 1,
      res: { wood: 2, brick: 0, sheep: 3, wheat: 1, ore: 1 } },
    { pid: 1, name: "Bob", vp: 2, resource_count: 9, dev_count: 2 }],
    rules_config: { target_vp: 10 }, legal: { pid: 0, settlements: [], roads: [], cities: [], ships: [],
      robber_tiles: [], pirate_tiles: [], robber_victims: {}, pirate_victims: {} }, ...overrides };
}
function render(Component, props) {
  buttons = [];
  const html = renderToStaticMarkup(React.createElement(Component, props));
  return { html, button: name => buttons.find(b => b.name === name) };
}
function renderGame(state = snapshot()) {
  const sent = [];
  return { ...render(GamePage, { client: { youPid: 0, sendCmd: cmd => sent.push(cmd) },
    match: { room_code: "ROOM", match_id: 4, tick: 7, state }, room: null, status: "connected",
    log: ["PRIVATE_LOG_SENTINEL"], error: null }), sent };
}

test("game defaults to the board scene with log/debug metadata closed and 3D selected", () => {
  const view = renderGame();
  assert.match(view.html, /class="board-stage"/);
  assert.doesNotMatch(view.html, /PRIVATE_LOG_SENTINEL|<dt>Tick|<dt>Phase|<dt>Pending|role="dialog"/);
  assert.equal(view.button("Event log")["aria-expanded"], false);
  assert.equal(view.button("Game info")["aria-expanded"], false);
  assert.equal(view.button("3D")["aria-pressed"], true);
  assert.equal(view.button("2D")["aria-pressed"], false);
});

test("Roll/End preserve turn/pending availability and send the existing command payloads", () => {
  let view = renderGame();
  assert.equal(view.button("Roll").disabled, false);
  assert.equal(view.button("End Turn").disabled, true);
  view.button("Roll").onClick();
  assert.deepEqual(view.sent, [{ type: "roll" }]);
  view = renderGame(snapshot({ rolled: true }));
  assert.equal(view.button("Roll").disabled, true);
  assert.equal(view.button("End Turn").disabled, false);
  view.button("End Turn").onClick();
  assert.deepEqual(view.sent, [{ type: "end_turn" }]);
  for (const state of [snapshot({ turn: 1 }), snapshot({ pending_action: "discard" }), snapshot({ phase: "setup" })])
    assert.equal(turnActions(state, 0).canRoll, false);
  assert.equal(turnActions(snapshot({ rolled: true, pending_action: "robber_move" }), 0).canEnd, false);
  assert.equal(turnActions(snapshot({ pending_action: "none" }), 0).canRoll, true);
});

test("player strip renders public scores/counts and never renders opponents' hidden payloads", () => {
  const state = snapshot();
  state.players[1].res = { PRIVATE_RES_SENTINEL: 41 };
  state.players[1].dev_cards = [{ type: "PRIVATE_VP_SENTINEL", new: false }];
  const view = render(GameTopBar, { state, pid: 0, roomCode: "ROOM", drawer: null, onInfo() {}, onLog() {} });
  assert.match(view.html, /Alice/); assert.match(view.html, /Bob/);
  assert.match(view.html, /9 resource cards/); assert.match(view.html, /2 development cards/);
  assert.match(view.html, /aria-current="true"/);
  assert.doesNotMatch(view.html, /PRIVATE_RES_SENTINEL|PRIVATE_VP_SENTINEL/);
});

test("resource hand renders all five resources, including explicit zero and missing counts", () => {
  const { html } = render(ResourceHand, { resources: { wood: 5, brick: 0, wheat: 2 } });
  for (const [name, count] of [["wood", 5], ["brick", 0], ["sheep", 0], ["wheat", 2], ["ore", 0]])
    assert.match(html, new RegExp(`aria-label="${name}: ${count}"`));
  assert.equal((html.match(/class="resource-card /g) || []).length, 5);
});

test("setup and ship prompts describe the next controller step without exposing raw phases/IDs", () => {
  const state = snapshot({ phase: "setup", setup_need: "settlement" });
  const interaction = createBoardInteraction(state, 0, emptySelection(), () => {}, () => {});
  assert.equal(contextPrompt(state, 0, interaction).title, "Place a settlement");
  state.setup_need = "road";
  assert.equal(contextPrompt(state, 0, interaction).title, "Choose a road");
  state.turn = 1;
  assert.equal(contextPrompt(state, 0, interaction).title, "Bob's turn");
  state.turn = 0; state.phase = "main";
  interaction.action = "move_ship";
  assert.equal(contextPrompt(state, 0, interaction).title, "Select a ship to move");
  interaction.selection.shipSource = [4, 5];
  assert.equal(contextPrompt(state, 0, interaction).title, "Choose its destination");
});

test("build palette uses existing personal legal lists, hides unavailable tools and invents no legality", () => {
  const legal = Object.freeze({ settlements: [7], roads: [], cities: [8], ships: [] });
  assert.deepEqual(buildTools({ legal }).map(t => t.id), ["settlement", "city"]);
  assert.deepEqual(buildTools({ legal: null }), []);
  assert.deepEqual(legal.roads, []);
});

test("drawer exposes a named close control and delegates dismissal; mandatory choices have modal semantics", () => {
  let closed = 0;
  const view = render(GameOverlay, { id: "game-log", title: "Event log", children: "kept event",
    onClose: () => closed++ });
  assert.match(view.html, /role="dialog" aria-modal="false"/);
  assert.match(view.html, /kept event/);
  view.button("Close Event log").onClick(); assert.equal(closed, 1);
  const modal = render(GameOverlay, { id: "gold-choice", title: "Gold Choice", modal: true, children: "Choose" });
  assert.match(modal.html, /aria-modal="true"/);
  assert.equal(modal.button("Close Gold Choice"), undefined);
});

test("Trade/Dev remain explicitly unavailable and game-over displays no active command controls", () => {
  const view = renderGame();
  for (const name of ["Trade", "Dev Card"]) {
    assert.equal(view.button(name).disabled, true);
    assert.equal(view.button(name)["aria-describedby"], "future-actions");
  }
  const finished = renderGame(snapshot({ game_over: true }));
  assert.match(finished.html, /Match complete/);
  for (const name of ["Roll", "Build", "End Turn"]) assert.equal(finished.button(name), undefined);
});
