import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";
import { PerspectiveCamera, Vector3 } from "three";

const require = createRequire(import.meta.url);
const compiled = await build({ stdin: { contents: `
  export * from "./src/board/publicTiles"; export * from "./src/board/fogReveal";
  export * from "./src/board3d/model"; export * from "./src/board3d/coordinates";
  export * from "./src/board3d/environment"; export * from "./src/board/interaction";
  export * from "./src/game/discovery"; export {eventText,default as GameEvents} from "./src/game/GameEvents";
  export {default as BoardView} from "./src/components/BoardView";
  export * from "./tests/fixtures/publicFog";`, resolveDir: fileURLToPath(new URL("../", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, format: "cjs", platform: "node", jsx: "automatic", external: ["react", "react/jsx-runtime"] });
let handlers = [];
const traced = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (props["data-tile-index"] != null) handlers.push(props);
  if (props.onClick) handlers.push(props);
  return jsxRuntime[name](type, props, key);
}])) };
const loaded = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  name => name === "react/jsx-runtime" ? traced : require(name), loaded, loaded.exports);
const { publicTileVisual, publicTileCenter, isKnownLand, isKnownSea, isHiddenTile, createRenderModel,
  advanceFogReveal, publicFogFixture, goldDiscoveryFixture, BoardView, GameEvents, eventText,
  isPublicDiscovery, goldDiscoveryReason, decorativeShipsEnabled, cameraFootprint, cameraFrame,
  createBoardInteraction, emptySelection } = loaded.exports;
const frame = (tiles, tick = 1, connected = true, key = "ROOM:1") => ({ tiles, tick, connected, key });
const hidden = { index: 0, center: [0, 0], terrain: "fog", visibility: "hidden", number: null };
const forest = { ...hidden, terrain: "forest", visibility: "revealed", number: 5 };
const start = tiles => advanceFogReveal(null, frame(tiles)).baseline;
function render(state, selection = emptySelection(), reveals) {
  handlers = []; const sent = [];
  const interaction = createBoardInteraction(state, 0, selection, () => {}, cmd => sent.push(cmd));
  const html = renderToStaticMarkup(React.createElement(BoardView, { state, interaction, reveals }));
  return { html, sent, interaction, clicks: [...handlers] };
}

test("public fixtures contain only safe hidden tiles and personal/public player fields", () => {
  for (const mode of ["hidden", "partial", "large", "normal"]) {
    const state = publicFogFixture(mode);
    assert.equal(state.players[1].res, undefined); assert.equal(state.players[1].dev_cards, undefined);
    for (const [i, tile] of state.tiles.entries()) {
      assert.equal(tile.index, i);
      if (tile.visibility === "hidden") { assert.equal(tile.terrain, "fog"); assert.equal(tile.number, null); }
    }
    assert.doesNotMatch(JSON.stringify(state), /assignment|seed|recipe|continuation|reward_ledger/);
  }
});

test("every hidden/malformed terrain alternative projects identically, never as land or sea", () => {
  for (const terrain of ["forest", "sea", "gold", "desert", "fog", "toString", "__proto__", "unexpected"]) {
    const tile = { ...hidden, terrain, number: 8 };
    assert.deepEqual(publicTileVisual(tile), { terrain: "fog", number: null, visibility: "hidden" });
    assert.equal(isKnownLand(tile), false); assert.equal(isKnownSea(tile), false); assert.equal(isHiddenTile(tile), true);
  }
  for (const malformed of [null, undefined, {}, { terrain: "gold", visibility: "unexpected" },
    { terrain: "forest", visibility: null }, { terrain: { nested: "sea" } }]) assert.equal(isHiddenTile(malformed), true);
});

test("historical non-Fog and explicit revealed terrain stay readable with validated tokens", () => {
  for (const terrain of ["forest", "hills", "pasture", "fields", "mountains", "desert", "gold", "sea"]) {
    assert.equal(publicTileVisual({ terrain, number: 6 }).terrain, terrain);
    assert.equal(publicTileVisual({ terrain, visibility: "revealed" }).visibility, "revealed");
  }
  assert.equal(publicTileVisual({ terrain: "wood" }).terrain, "forest");
  for (const number of ["8", {}, NaN, 7, 1, 13, 4.5, null]) assert.equal(publicTileVisual({ terrain: "gold", number }).number, null);
});

test("public geometry uses centers or axial coordinates and missing/malformed values remain finite", () => {
  assert.deepEqual(publicTileCenter({ center: [116, 58], q: 10, r: 10 }, 58), [116, 58]);
  assert.deepEqual(publicTileCenter({ center: [NaN, Infinity], q: 1, r: 2 }, 58), [58 * Math.sqrt(3) * 2, 174]);
  for (const tile of [null, {}, { center: "bad", q: NaN, r: Infinity }]) assert.deepEqual(publicTileCenter(tile, 58), [0, 0]);
  assert.doesNotMatch(render({ ...publicFogFixture(), tiles: [] }).html, /Infinity|NaN/);
  for (const size of [NaN, -10, Infinity, null]) assert.doesNotMatch(render({ ...publicFogFixture(), size }).html, /Infinity|NaN/);
});

test("SVG hidden tiles have neutral art/title, no number, resource or figure even with malformed contents", () => {
  const state = publicFogFixture("hidden");
  state.tiles[0] = { ...state.tiles[0], terrain: "gold", number: 8 };
  state.robber_tile = 0; state.pirate_tile = 0;
  const { html } = render(state);
  assert.equal((html.match(/data-terrain="fog"/g) ?? []).length, 7);
  assert.doesNotMatch(html, /data-number-token|gold|>R<|>P</);
  assert.match(html, /Hex 0: unexplored/); assert.match(html, /fog-svg-mark/);
});

test("SVG known tiles show exact public tokens and both 3:1 and specialized ports", () => {
  const { html } = render(publicFogFixture());
  assert.match(html, /data-number-token="5"/); assert.match(html, /data-number-token="8"/);
  assert.match(html, /data-terrain="forest"/); assert.match(html, /data-terrain="sea"/);
  assert.match(html, /data-terrain="desert"/); assert.match(html, />2:1</); assert.match(html, />3:1</);
});

test("3D model contains only sanitized terrain/numbers/visibility and preserves graph/pieces", () => {
  const state = publicFogFixture();
  state.tiles[3] = { ...state.tiles[3], terrain: "sea", number: 8 };
  const before = JSON.stringify(state); const model = createRenderModel(state);
  assert.equal(JSON.stringify(state), before); assert.deepEqual(model.tiles[3], {
    tileIndex: 3, position: [state.tiles[3].center[0] / 58, 0, state.tiles[3].center[1] / 58],
    terrain: "fog", visibility: "hidden", number: null });
  assert.equal(model.roads.length, 1); assert.equal(model.ships.length, 1); assert.equal(model.buildings.length, 2);
  assert.deepEqual(model.roads[0].edge.join(","), Object.keys(state.occupied_e)[0]);
  assert.deepEqual(model.robbers.map(r => r.tileIndex), [5]); assert.equal(model.pirate.tileIndex, 1);
  assert.equal(decorativeShipsEnabled(publicFogFixture("hidden")), false);
});

test("coasts and ports require known adjacency; hidden sea and land cannot change any geometry", () => {
  const original = publicFogFixture(), reference = createRenderModel(original);
  for (const terrain of ["sea", "forest", "gold", "desert"]) {
    const state = structuredClone(original); state.tiles[3].terrain = terrain; state.tiles[3].number = 8;
    assert.deepEqual(createRenderModel(state), reference);
  }
  assert.ok(reference.coast.length > 0);
  for (const coast of reference.coast) assert.ok(original.edge_adj_hexes[coast.edge.join(",")].every(i => !isHiddenTile(original.tiles[i])));
  const edge = original.edges.find(e => original.edge_adj_hexes[e.join(",")].includes(3));
  const state = { ...original, ports: [[edge, "2:1:ore"]] };
  assert.equal(createRenderModel(state).ports.length, 0); assert.doesNotMatch(render(state).html, />2:1</);
  state.edge_adj_hexes = { ...state.edge_adj_hexes, [edge.join(",")]: [999] };
  assert.equal(createRenderModel(state).ports.length, 0);
});

test("server road/ship/setup/free/movement/build targets near Fog are retained without local inference", () => {
  const state = publicFogFixture();
  for (const action of ["road", "ship", "settlement", "city"]) {
    const { interaction } = render(state, { ...emptySelection(), action });
    if (["road", "ship"].includes(action)) {
      assert.deepEqual(interaction.targets.edges, state.legal[action === "road" ? "roads" : "ships"]);
    } else assert.deepEqual(interaction.targets.vertices, state.legal[action === "city" ? "cities" : "settlements"]);
  }
  state.phase = "setup"; state.setup_need = "road";
  const setup = render(state, { ...emptySelection(), action: "ship" });
  setup.interaction.onEdgeClick(state.legal.ships[0]);
  assert.deepEqual(setup.sent, [{ type: "build_ship", eid: state.legal.ships[0], setup: true }]);
  state.phase = "main"; state.legal.road_free = true;
  const free = render(state, { ...emptySelection(), action: "road" }); free.interaction.onEdgeClick(state.legal.roads[0]);
  assert.equal(free.sent[0].type, "place_road"); assert.equal(free.sent[0].free, true);
  const from = state.legal.move_ship.sources[0];
  const move = render(state, { ...emptySelection(), action: "move_ship", shipSource: from });
  move.interaction.onEdgeClick(state.legal.move_ship.targets[from.join(",")][0]);
  assert.equal(move.sent[0].type, "move_ship"); assert.deepEqual(move.sent[0].from_eid, from);
});

test("initial/refresh/rematch visibility establishes a baseline, newer committed reveal keeps original ID", () => {
  assert.deepEqual(advanceFogReveal(null, frame([forest])).revealed, []);
  const previous = start([hidden]);
  const next = advanceFogReveal(previous, frame([forest], 2)); assert.deepEqual(next.revealed, [0]);
  assert.deepEqual(advanceFogReveal(next.baseline, frame([forest], 3)).revealed, []);
  assert.deepEqual(advanceFogReveal(previous, frame([forest], 2, true, "ROOM:2")).revealed, []);
});

test("duplicate/stale/rejected snapshots cannot replay a reveal or replace its freshness baseline", () => {
  const previous = start([hidden]);
  for (const tick of [0, 1, -1, null, NaN, Infinity, 1.5]) { const next = advanceFogReveal(previous, frame([forest], tick));
    assert.equal(next.baseline, previous); assert.deepEqual(next.revealed, []); }
  const next = advanceFogReveal(previous, frame([forest], 2));
  const stale = advanceFogReveal(next.baseline, frame([hidden], 1)); assert.equal(stale.baseline, next.baseline);
  assert.deepEqual(advanceFogReveal(stale.baseline, frame([forest], 3)).revealed, []);
});

test("reconnect ignores cached visibility and baselines the first fresh snapshot, then resumes live reveals", () => {
  const initial = [hidden, hidden];
  const offline = advanceFogReveal(start(initial), frame(initial, 1, false)).baseline;
  const cached = advanceFogReveal(offline, frame(initial, 1)).baseline;
  assert.equal(cached.awaitingFresh, true);
  const fresh = advanceFogReveal(cached, frame([forest, hidden], 4)); assert.deepEqual(fresh.revealed, []);
  assert.deepEqual(advanceFogReveal(fresh.baseline, frame([forest, forest], 5)).revealed, [1]);
  const equal = advanceFogReveal(cached, frame([...initial], 1)); assert.equal(equal.baseline.awaitingFresh, false);
});

test("50 public hexes fit the perspective camera in desktop and narrower canvases", () => {
  const model = createRenderModel(publicFogFixture("large")), footprint = cameraFootprint(model);
  assert.equal(model.tiles.length, 50);
  for (const aspect of [1.8, 1.1, .75]) {
    const fit = cameraFrame(model.bounds, aspect, 38, footprint), camera = new PerspectiveCamera(38, aspect, .1, 1000);
    camera.position.set(...fit.position); camera.lookAt(...fit.target); camera.updateMatrixWorld(true);
    for (const point of footprint) { const p = new Vector3(...point).project(camera); assert.ok(Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1); }
  }
});

test("discovery log displays only revealed public contents and authoritative public rewards", () => {
  const state = goldDiscoveryFixture(), gold = state.game_events[1];
  assert.equal(eventText(gold, state.players, state.tiles), "Explorer discovered hex 2: gold (8); reward: choose 1 resource from the bank");
  assert.match(eventText({ ...gold, tile: 0, terrain: "forest", number: 5, reward: { kind: "resource", resource: "wood", quantity: 1 } }, state.players, state.tiles), /reward: 1 wood/);
  for (const [tile, terrain] of [[1, "sea"], [5, "desert"]]) assert.match(eventText({ ...gold, tile, terrain, number: null,
    reward: { kind: "none", quantity: 0 } }, state.players, state.tiles), /no discovery reward/);
  assert.match(eventText({ ...gold, reward: { kind: "gold_choice", quantity: 0 } }, state.players, state.tiles), /unavailable/);
  const hiddenEvent = { ...gold, tile: 3, terrain: "gold", number: 8 };
  assert.equal(isPublicDiscovery(hiddenEvent, state.tiles), false);
  state.game_events = [hiddenEvent]; const html = renderToStaticMarkup(React.createElement(GameEvents, { state }));
  assert.doesNotMatch(html, /gold|discover_tile/); assert.match(html, /No gameplay events yet/);
});

test("Gold choices never disclose their private selection and only pending current discovery explains the modal", () => {
  const state = goldDiscoveryFixture(); assert.match(goldDiscoveryReason(state, 0), /Discovery reward/);
  assert.equal(goldDiscoveryReason(state, 1), null);
  const choice = { id: 3, tick: 3, at_ms: 2000, actor_pid: 0, type: "choose_gold", gained: { ore: 1 } };
  assert.equal(eventText(choice, state.players, state.tiles), "Explorer collected gold resources");
  const malformedReward = { ...state.game_events[1], reward: { kind: "gold_choice", quantity: 1, resource: "ore" } };
  assert.doesNotMatch(eventText(malformedReward, state.players, state.tiles), /\bore\b/);
  state.game_events.push(choice); assert.match(goldDiscoveryReason(state, 0), /Discovery reward/);
  state.game_events.push({ ...choice, id: 4, tick: 4, type: "roll" }); assert.equal(goldDiscoveryReason(state, 0), null);
  state.pending_action = null; assert.equal(goldDiscoveryReason(state, 0), null);
});
