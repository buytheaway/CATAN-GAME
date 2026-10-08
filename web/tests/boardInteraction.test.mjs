import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const compiled = await build({ entryPoints: [fileURLToPath(new URL("../src/board/interaction.ts", import.meta.url))],
  bundle: true, write: false, platform: "node", format: "esm" });
const { createBoardInteraction, emptySelection, interactionTargets, reconcileSelection } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

const state = () => ({ phase: "main", legal: { pid: 0, settlements: [7], cities: [9], roads: [[7, 9]], ships: [[9, 11]],
  road_free: false, robber_tiles: [], pirate_tiles: [], robber_victims: {}, pirate_victims: {},
  move_ship: { sources: [[11, 12]], targets: { "11,12": [[12, 13]] } } } });
function controller(snapshot = state(), action = null) {
  let selection = { ...emptySelection(), action };
  const sent = [];
  return { sent, selection: () => selection,
    get ui() { return createBoardInteraction(snapshot, 0, selection, next => { selection = next; }, cmd => sent.push(cmd)); },
    synchronize(next = snapshot) { snapshot = next; selection = reconcileSelection(selection, snapshot, 0); },
  };
}

test("data to highlights uses only the action's personal server lists, with no geometry fallback", () => {
  const s = state();
  assert.deepEqual(interactionTargets(s, 0, { ...emptySelection(), action: "city" }).targets.vertices, [9]);
  assert.deepEqual(interactionTargets(s, 1, { ...emptySelection(), action: "city" }).targets.vertices, []);
  assert.deepEqual(interactionTargets({ ...s, legal: undefined }, 0, { ...emptySelection(), action: "road" }).targets.edges, []);
});

test("vertex clicks use existing settlement/city commands and ignore illegal IDs", () => {
  for (const [action, vid, expected] of [["settlement", 7, { type: "place_settlement", vid: 7, setup: false }],
                                        ["city", 9, { type: "upgrade_city", vid: 9 }]]) {
    const c = controller(state(), action);
    c.ui.onVertexClick(999);
    assert.deepEqual(c.sent, []);
    c.ui.onVertexClick(vid);
    assert.deepEqual(c.sent, [expected]);
    c.ui.onVertexClick(vid);
    assert.equal(c.sent.length, 1); // waiting feedback prevents duplicate clicks
  }
});

test("setup automatically follows snapshot step and uses the same existing commands", () => {
  const s = { ...state(), phase: "setup", setup_need: "settlement" };
  const c = controller(s);
  c.ui.onVertexClick(7);
  assert.deepEqual(c.sent[0], { type: "place_settlement", vid: 7, setup: true });
  c.synchronize({ ...s, setup_need: "road" });
  c.ui.onEdgeClick([9, 7]);
  assert.deepEqual(c.sent[1], { type: "place_road", eid: [7, 9], setup: true });
});

test("road and ship payloads preserve server edge IDs and server free-road choice", () => {
  const s = state(); s.legal.road_free = true;
  const road = controller(s, "road");
  road.ui.onEdgeClick([9, 7]);
  assert.deepEqual(road.sent, [{ type: "place_road", eid: [7, 9], setup: false, free: true }]);
  const ship = controller(s, "ship");
  ship.ui.onEdgeClick([11, 9]);
  assert.deepEqual(ship.sent, [{ type: "build_ship", eid: [9, 11], free: true }]);
});

test("Seafarers setup selects a ship from authoritative targets and keeps the original IDs", () => {
  const s = { ...state(), phase: "setup", setup_need: "road" };
  const c = controller(s);
  c.ui.onSelectAction("ship");
  assert.equal(c.ui.action, "ship");
  assert.deepEqual(c.ui.targets.edges, s.legal.ships);
  c.ui.onEdgeClick([7, 9]);
  assert.deepEqual(c.sent, []);
  c.ui.onEdgeClick([11, 9]);
  assert.deepEqual(c.sent, [{ type: "build_ship", eid: [9, 11], setup: true }]);
  c.synchronize({ ...s, setup_need: "settlement" });
  assert.equal(c.ui.action, "settlement");
});

test("paid ship command stays unchanged and missing personal targets never sends a setup ship", () => {
  const c = controller(state(), "ship");
  c.ui.onEdgeClick([9, 11]);
  assert.deepEqual(c.sent, [{ type: "build_ship", eid: [9, 11] }]);
  const invalid = controller({ ...state(), phase: "setup", setup_need: "road", legal: undefined }, "ship");
  invalid.ui.onEdgeClick([9, 11]);
  assert.deepEqual(invalid.sent, []);
});

test("move ship selects source then only a server-provided destination", () => {
  const c = controller(state(), "move_ship");
  c.ui.onEdgeClick([12, 11]);
  assert.deepEqual(c.sent, []);
  assert.deepEqual(c.selection().shipSource, [11, 12]);
  assert.deepEqual(c.ui.targets.edges, [[12, 13]]);
  c.ui.onEdgeClick([7, 9]);
  assert.deepEqual(c.sent, []);
  c.ui.onEdgeClick([13, 12]);
  assert.deepEqual(c.sent, [{ type: "move_ship", from_eid: [11, 12], to_eid: [12, 13] }]);
});

test("robber and pirate use legal tile/victim IDs and require an explicit choice for multiple victims", () => {
  const s = state(); s.legal.robber_tiles = [1]; s.legal.pirate_tiles = [2];
  s.legal.robber_victims = { 1: [1, 2] }; s.legal.pirate_victims = { 2: [2] };
  const c = controller(s);
  c.ui.onTileClick(1);
  assert.deepEqual(c.sent, []);
  assert.deepEqual(c.selection().victim.victims, [1, 2]);
  c.ui.onVictimClick(999); assert.deepEqual(c.sent, []);
  c.ui.onVictimClick(2);
  assert.deepEqual(c.sent, [{ type: "move_robber", tile: 1, victim: 2 }]);
  const pirate = controller(s);
  pirate.ui.onTileClick(2);
  assert.deepEqual(pirate.sent, [{ type: "move_pirate", tile: 2, victim: 2 }]);
});

test("no-victim tile sends movement without a victim; invalid tile never sends", () => {
  const s = state(); s.legal.robber_tiles = [1];
  const c = controller(s);
  c.ui.onTileClick(99); assert.deepEqual(c.sent, []);
  c.ui.onTileClick(1); assert.deepEqual(c.sent, [{ type: "move_robber", tile: 1 }]);
});

test("fresh snapshots invalidate removed sources/victims and clear local waiting feedback", () => {
  const c = controller(state(), "move_ship");
  c.ui.onEdgeClick([11, 12]);
  const next = state(); next.legal.move_ship.sources = [];
  c.synchronize(next); assert.equal(c.selection().shipSource, null);
  const choice = { ...emptySelection(), victim: { type: "move_robber", tile: 5, victims: [2] }, waiting: true };
  assert.deepEqual(reconcileSelection(choice, next, 0), emptySelection());
});

test("one controller supplies renderer-neutral targets without mutating the frozen snapshot", () => {
  const s = state(); const before = JSON.stringify(s);
  function freeze(obj) { Object.values(obj).forEach(v => v && typeof v === "object" && freeze(v)); Object.freeze(obj); }
  freeze(s);
  const c = controller(s, "move_ship"); c.ui.onEdgeClick([11, 12]);
  const svgProps = c.ui; const threeProps = c.ui;
  assert.deepEqual(svgProps.targets, threeProps.targets);
  assert.deepEqual(threeProps.selection.shipSource, [11, 12]);
  threeProps.onEdgeClick([12, 13]);
  assert.equal(JSON.stringify(s), before);
});

test("City targets exclude empty/opponent vertices and rejection restores targeting without optimistic occupancy", () => {
  const s = { ...state(), vertices: { 7: [0, 0], 9: [58, 0], 11: [0, 58] },
    occupied_v: { 7: [0, 1], 9: [1, 1] } };
  s.legal.cities = [7];
  const before = JSON.stringify(s), c = controller(s, "city");
  assert.deepEqual(c.ui.targets.vertices, [7]);
  c.ui.onVertexClick(9); c.ui.onVertexClick(11); assert.deepEqual(c.sent, []);
  c.ui.onVertexClick(7); assert.deepEqual(c.sent, [{ type: "upgrade_city", vid: 7 }]);
  assert.equal(c.selection().waiting, true); assert.deepEqual(c.ui.targets.vertices, []);
  assert.equal(JSON.stringify(s), before);
  // Rejected command supplies unchanged authoritative state. Selection is ready for retry.
  c.synchronize(s); assert.equal(c.selection().waiting, false);
  assert.deepEqual(c.ui.targets.vertices, [7]); assert.deepEqual(s.occupied_v[7], [0, 1]);
});
