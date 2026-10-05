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
    export {default as TradePanel,TradeOffers} from "./game/TradePanel";
    export {default as DevelopmentPanel,DevelopmentHand} from "./game/DevelopmentCards";
    export {default as ActionButton} from "./game/ActionButton";
    export {default as BoardControls} from "./board/BoardControls";
    export {default as DiceHUD} from "./game/DiceHUD";
    export {default as Endgame} from "./game/Endgame";
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
  return { ...render(GamePage, { client: { youPid: 0, isOpen: () => true,
    sendCmd: cmd => { sent.push(cmd); return `command-${sent.length}`; } },
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

test("direct build tools retain zero counts from personal legal lists without inventing targets", () => {
  const legal = Object.freeze({ settlements: [7], roads: [], cities: [8], ships: [] });
  assert.deepEqual(buildTools({ legal }).map(t => [t.id, t.count]),
    [["road", 0], ["settlement", 1], ["city", 1], ["ship", 0]]);
  assert.ok(buildTools({ legal: null }).every(t => t.count === 0));
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

test("dock purchase sends one buy intent, with no optimistic card, Build menu or Trade button", () => {
  const state = snapshot({ rolled: true });
  const before = JSON.stringify(state);
  const view = renderGame(state);
  assert.equal(view.button("Trade"), undefined);
  assert.equal(view.button("Build"), undefined);
  assert.equal(view.button("Dev Card").disabled, false);
  assert.equal(view.button("Dev Card")["aria-haspopup"], undefined);
  view.button("Dev Card").onClick(); view.button("Dev Card").onClick();
  assert.deepEqual(view.sent, [{ type: "buy_dev" }]);
  assert.equal(JSON.stringify(state), before);
  assert.equal(renderGame(snapshot()).button("Dev Card").disabled, true);
  const finished = renderGame(snapshot({ game_over: true }));
  assert.match(finished.html, /Match complete/);
  for (const name of ["Roll", "Road", "Settlement", "City", "Dev Card", "End Turn"])
    assert.equal(finished.button(name), undefined);
});

test("development hand/details use only self cards and passive VP never has a Play action", () => {
  const { DevelopmentHand, DevelopmentPanel } = loaded.exports;
  const state = snapshot({ dev_played_turn: { "0": false }, bank_available: { wood: true }, rolled: true });
  state.players[0].dev_cards = [{ type: "victory_point", new: false }, { type: "knight", new: true }];
  state.players[1].dev_cards = [{ type: "PRIVATE_CARD_SENTINEL", new: false }];
  const hand = render(DevelopmentHand, { state, pid: 0, onCard() {} });
  assert.match(hand.html, /Victory Point/); assert.match(hand.html, /Knight/);
  assert.doesNotMatch(hand.html, /PRIVATE_CARD_SENTINEL/);
  const sent = [];
  const props = { state, pid: 0, waiting: false, error: null, submit: cmd => sent.push(cmd), onClose() {}, onBoardPlay() {} };
  let panel = render(DevelopmentPanel, { ...props, selected: "victory_point" });
  assert.equal(panel.button("Play Victory Point"), undefined);
  panel = render(DevelopmentPanel, { ...props, selected: "knight" });
  assert.equal(panel.button("Play Knight").disabled, true);
  state.players[0].dev_cards[1].new = false;
  panel = render(DevelopmentPanel, { ...props, selected: "knight" });
  panel.button("Play Knight").onClick();
  assert.equal(panel.button("Buy Dev Card"), undefined);
  assert.deepEqual(sent, [{ type: "play_dev", card: "knight" }]);
});

test("bank and player offer buttons keep the existing payloads and rejection message", () => {
  const { TradePanel, TradeOffers } = loaded.exports;
  const state = snapshot({ rolled: true, bank_available: { ore: true } });
  state.players[0].res.wood = 4;
  const sent = [];
  const props = { state, pid: 0, waiting: false, submit: cmd => sent.push(cmd) };
  const panel = render(TradePanel, { ...props, draft: { give: { wood: 4 }, want: { ore: 1 }, target: "bank" },
    onChange() {}, targets: [], onClose() {}, error: { message: "Bank has not enough resources" } });
  assert.match(panel.html, /Bank has not enough resources/);
  panel.button("Trade with bank").onClick();
  assert.deepEqual(sent.pop(), { type: "trade_bank", give: "wood", get: "ore", get_qty: 1 });
  state.trade_offers = [{ offer_id: 17, from_pid: 0, to_pid: 1, give: { wood: 2 }, get: { ore: 1 }, status: "active" }];
  const recipient = render(TradeOffers, { ...props, pid: 1 });
  assert.equal(recipient.button("Accept").disabled, true); // Missing private ore, no invented opponent hand.
  recipient.button("Reject").onClick();
  assert.deepEqual(sent.pop(), { type: "trade_offer_decline", offer_id: 17 });
  const creator = render(TradeOffers, props);creator.button("Cancel offer").onClick();
  assert.deepEqual(sent.pop(), { type: "trade_offer_cancel", offer_id: 17 });
});

test("Ship exists only when server rules enable ships; setup shows only its required action", () => {
  for (const rules of [{}, { enable_seafarers: false }, { enable_seafarers: true, max_ships: 0 }]) {
    const view = renderGame(snapshot({ rolled: true, rules_config: rules,
      legal: { ...snapshot().legal, ships: [[1, 2]], settlements: [7] } }));
    assert.equal(view.button("Ship"), undefined);
    assert.ok(view.button("Road")); assert.ok(view.button("Settlement")); assert.ok(view.button("City"));
    assert.equal(view.button("Road").disabled, true);
    assert.equal(view.button("Settlement").disabled, false);
  }
  const sea = renderGame(snapshot({ rolled: true, rules_config: { enable_seafarers: true, max_ships: 15 },
    legal: { ...snapshot().legal, ships: [[1, 2]] } }));
  assert.equal(sea.button("Ship").disabled, false);
  for (const need of ["settlement", "road"]) {
    const view = renderGame(snapshot({ phase: "setup", setup_need: need,
      legal: { ...snapshot().legal, settlements: [7], roads: [[1, 2]], ships: [[1, 2]] } }));
    assert.ok(view.button(need === "settlement" ? "Settlement" : "Road"));
    for (const label of [need === "settlement" ? "Road" : "Settlement", "City", "Ship", "Dev Card", "End Turn"])
      assert.equal(view.button(label), undefined);
  }
});

test("cost preview exposes exact quantities and missing resources even for keyboard focus on disabled actions", () => {
  const { ActionButton } = loaded.exports;
  const view = render(ActionButton, { action: "city", label: "City", icon: "city", resources: { wheat: 2, ore: 2 },
    disabled: true, onClick() {} });
  assert.match(view.html, /tabindex="0"/);
  assert.match(view.html, /role="tooltip"/);
  assert.match(view.html, /data-available="true" aria-label="wheat ×2: owned"/);
  assert.match(view.html, /data-available="false" aria-label="ore ×3: missing"/);
  assert.match(view.html, /×3/);
  assert.equal(view.button("City").disabled, true);
  const free = render(ActionButton, { action: "road", label: "Road", icon: "road", resources: {}, free: true, onClick() {} });
  assert.match(free.html, /Free placement/);
  assert.doesNotMatch(free.html, /data-resource=/);
});

test("resource hand delegates repeated card clicks without mutating snapshot resources", () => {
  const resources = Object.freeze({ wood: 2, brick: 0 });
  const clicked = [];
  const view = render(ResourceHand, { resources, onResource: r => clicked.push(r) });
  view.button("Give wood (2 owned)").onClick(); view.button("Give wood (2 owned)").onClick();
  assert.deepEqual(clicked, ["wood", "wood"]);
  assert.equal(view.button("Give brick (0 owned)").disabled, true);
  assert.deepEqual(resources, { wood: 2, brick: 0 });
});

test("Trade Tray adds and removes Give/Want cards and preserves targeted multi-resource terms", () => {
  const { TradePanel } = loaded.exports;
  const state = snapshot({ rolled: true });
  let changed; const sent = [];
  const draft = Object.freeze({ give: { wood: 2, sheep: 1 }, want: { ore: 1, wheat: 1 }, target: "1" });
  const view = render(TradePanel, { state, pid: 0, draft, targets: [{ pid: 1, name: "Bob" }],
    onChange: value => changed = value, waiting: false, error: null, submit: cmd => sent.push(cmd), onClose() {} });
  assert.match(view.html, /aria-modal="false"/);
  assert.doesNotMatch(view.html, /type="number"/);
  view.button("Want ore").onClick(); assert.deepEqual(changed.want, { ore: 2, wheat: 1 });
  view.button("Remove wanted wheat").onClick(); assert.deepEqual(changed.want, { ore: 1 });
  view.button("Remove give wood").onClick(); assert.deepEqual(changed.give, { wood: 1, sheep: 1 });
  view.button("Send offer").onClick();
  assert.deepEqual(sent, [{ type: "trade_offer_create", give: { wood: 2, sheep: 1 }, get: { wheat: 1, ore: 1 }, to_pid: 1 }]);
  assert.deepEqual(draft.give, { wood: 2, sheep: 1 });
});

test("bank tray renders actual owned-port ratios and disables incomplete or unavailable exchanges", () => {
  const { TradePanel } = loaded.exports;
  for (const [ratio, ports] of [[4, []], [3, [[[12, 13], "3:1"]]], [2, [[[12, 13], "2:1:wood"]]]]) {
    const state = snapshot({ rolled: true, occupied_v: { "12": [0, 1] }, ports, bank_available: { ore: true } });
    state.players[0].res.wood = ratio;
    const props = { state, pid: 0, targets: [], onChange() {}, waiting: false, error: null, submit() {}, onClose() {} };
    const draft = { give: { wood: ratio }, want: { ore: 1 }, target: "bank" };
    const view = render(TradePanel, { ...props, draft });
    assert.match(view.html, new RegExp(`aria-label="Trade ratio ${ratio}:1"`));
    assert.equal(view.button("Trade with bank").disabled, false);
    assert.equal(render(TradePanel, { ...props, draft: { ...draft, give: { wood: ratio - 1 } } }).button("Trade with bank").disabled, true);
    state.bank_available.ore = false;
    assert.equal(render(TradePanel, { ...props, draft }).button("Trade with bank").disabled, true);
  }
});

test("Dice HUD renders exact server faces and never invents a pair from a legacy sum", () => {
  const { DiceHUD } = loaded.exports;
  const exact = render(DiceHUD, { faces: [4, 5], total: 9, roll: null });
  assert.match(exact.html, /data-face="4"/); assert.match(exact.html, /data-face="5"/);
  assert.equal((exact.html.match(/class="die-pip"/g) || []).length, 9);
  const legacy = render(DiceHUD, { faces: null, total: 9, roll: null });
  assert.doesNotMatch(legacy.html, /data-face="[1-6]"/);
  assert.match(legacy.html, /faces unavailable/);
});

test("secondary bank view renders public availability without inventing exact amounts", () => {
  const { html } = render(loaded.exports.BankSummary, { available: { wood: true, brick: false, sheep: true, wheat: true, ore: true } });
  assert.match(html, /aria-label="wood: available"/); assert.match(html, /aria-label="brick: unavailable"/);
  assert.doesNotMatch(html, /<b>19|data-count=/);
});

test("results use server winner/final scores and delegate rematch/exit without creating a match", () => {
  const { Endgame } = loaded.exports;
  const state = snapshot({ game_over: true, winner_pid: 1 });
  state.players[0].vp = 8; state.players[1].vp = 10;
  state.players[1].dev_cards = [{ type: "PRIVATE_RESULTS_SENTINEL", new: false }];
  const room = { room_code: "ROOM", status: "in_match", host_pid: 0, players: state.players.map(p => ({ ...p, connected: true })) };
  let rematches = 0, exits = 0;
  const view = render(Endgame, { state, pid: 0, room, connected: true, matchKey: "ROOM:1", error: null,
    onRematch: () => rematches++, onLobby: () => exits++ });
  assert.match(view.html, /Bob/);assert.match(view.html, /10 VP/);assert.match(view.html, /8 VP/);
  assert.doesNotMatch(view.html, /PRIVATE_RESULTS_SENTINEL/);
  assert.equal(view.button("Rematch").disabled, false);
  view.button("Rematch").onClick(); view.button("Back to Lobby").onClick();
  assert.equal(rematches, 1);assert.equal(exits, 1);assert.equal(state.game_over, true);
});
