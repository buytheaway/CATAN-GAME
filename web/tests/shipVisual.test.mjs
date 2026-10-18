import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";

const compiled = await build({ stdin: { contents: `export * from "./src/board/shipFeedback";
  export * from "./src/board3d/shipMotion"; export * from "./tests/fixtures/publicShips";`,
  resolveDir: fileURLToPath(new URL("../", import.meta.url)), loader: "tsx" }, bundle: true, write: false,
  format: "cjs", platform: "node", external: ["react"] });
const module = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  createRequire(import.meta.url), module, module.exports);
const { advanceShipFeedback: advance, shipPose, shipDeparture, SHIP_BUILD_MS, SHIP_MOVE_MS,
  SHIP_DEPART_MS, publicShipFixture, shipPreviewChange } = module.exports;
const a = "0,1", b = "1,2", c = "2,3";
const frame = (ships, tick = 1, events = [], connected = true, key = "ROOM:1") => ({ ships, tick, events, connected, key });
const base = (ships = { [a]: 0 }) => advance(null, frame(ships)).baseline;
const move = (actor_pid = 0, tick = 2, id = 1) => ({ type: "move_ship", actor_pid, tick, id });
const cue = kind => ({ kind, from: [0, 1], to: [1, 2], owner: 0, started: 100 });

test("restored public ships and historical events establish a quiet baseline", () => {
  assert.deepEqual(advance(null, frame({ [a]: 0 }, 10, [move(0, 9)] )).changes, []);
});
test("a new accepted ship is construction; existing ships never reappear", () => {
  const result = advance(base(), frame({ [a]: 0, [b]: 0 }, 2));
  assert.deepEqual(result.changes, [{ kind: "build", to: [1, 2], owner: 0 }]);
  assert.deepEqual(advance(result.baseline, frame({ [a]: 0, [b]: 0 }, 3)).changes, []);
});
test("only an adjacent committed tick plus fresh public move event identifies one unambiguous transfer", () => {
  assert.deepEqual(advance(base(), frame({ [b]: 0 }, 2, [move()])).changes,
    [{ kind: "move", from: [0, 1], to: [1, 2], owner: 0 }]);
});
test("a removed/added edge without authoritative movement evidence snaps without guessed identity", () => {
  for (const events of [[], [{ ...move(), type: "build_ship" }], [move(1)], [move(0, 1)], [move(0, 2, 1.5)], [move(), move(0, 2, 2)]])
    assert.deepEqual(advance(base(), frame({ [b]: 0 }, 2, events)).changes, []);
});
test("multiple removed/added ships do not invent a matching or movement route", () => {
  assert.deepEqual(advance(base({ [a]: 0, [b]: 0 }), frame({ [c]: 0, "3,4": 0 }, 2, [move()])).changes, []);
});
test("owner replacement or mismatched ownership is never treated as movement", () => {
  for (const ships of [{ [a]: 1 }, { [b]: 1 }]) assert.deepEqual(advance(base(), frame(ships, 2, [move()])).changes, []);
});
test("coalesced ticks cannot conceal move/build operations behind a guessed construction", () => {
  assert.deepEqual(advance(base(), frame({ [b]: 0 }, 4, [move(0, 4)])).changes, []);
  assert.deepEqual(advance(base(), frame({ [a]: 0, [b]: 0 }, 4)).changes, []);
});
test("duplicate, rejected/equal and stale frames retain the current baseline without feedback", () => {
  const previous = base();
  for (const tick of [1, 0, -1, NaN]) {
    const result = advance(previous, frame({ [b]: 0 }, tick, [move()]));
    assert.equal(result.baseline, previous); assert.deepEqual(result.changes, []);
  }
});
test("an already observed public event ID cannot cause a second movement", () => {
  const previous = advance(null, frame({ [a]: 0 }, 1, [move(0, 1, 7)])).baseline;
  assert.deepEqual(advance(previous, frame({ [b]: 0 }, 2, [move(0, 2, 7)])).changes, []);
});
test("disconnect, cached reconnect and the first fresh frame never replay offline discoveries", () => {
  const ships = { [a]: 0 };
  let previous = advance(null, frame(ships)).baseline;
  previous = advance(previous, frame(ships, 1, [], false)).baseline;
  previous = advance(previous, frame(ships)).baseline; assert.equal(previous.awaitingFresh, true);
  const fresh = advance(previous, frame({ [b]: 0 }, 2, [move()]));
  assert.deepEqual(fresh.changes, []); assert.equal(fresh.baseline.awaitingFresh, false);
  assert.equal(advance(fresh.baseline, frame({ [b]: 0, [c]: 0 }, 3)).changes.length, 1);
});
test("new room/match scopes baseline even if edge IDs/ticks coincide", () => {
  for (const key of ["ROOM:2", "OTHER:1"]) assert.deepEqual(advance(base(), frame({ [b]: 0 }, 2, [move()], true, key)).changes, []);
});
test("removal alone is not construction and simultaneous additions retain each owner", () => {
  assert.deepEqual(advance(base(), frame({}, 2)).changes, []);
  assert.deepEqual(advance(base({}), frame({ [a]: 0, [b]: 1 }, 2)).changes.map(c => c.owner), [0, 1]);
});
test("malformed public IDs or owners do not create animation identities", () => {
  const result = advance(base({}), frame({ bad: 0, "2,1": 0, "0,0": 0, "1,NaN": 0, "1,2": -1, "2,3": undefined }, 2));
  assert.deepEqual(result.changes, []);
});
test("animation classification has no access to terrain, rules, hands or predictions", () => {
  const input = frame(Object.freeze({ [a]: 0, [b]: 0 }), 2);
  for (const key of ["tiles", "terrain", "rules", "res", "assignment", "cmd"])
    Object.defineProperty(input, key, { enumerable: true, get() { throw Error("Private field read: " + key); } });
  const before = base(); assert.equal(advance(before, input).changes.length, 1);
  assert.deepEqual([...before.occupancy], [[a, 0]]);
});
test("construction emergence is finite and has no planar translation", () => {
  const early = shipPose([1, 2], 0, cue("build"), 100);
  assert.equal(early.active, true); assert(early.scale[1] < 1 && early.y < -.1);
  const end = shipPose([1, 2], 0, cue("build"), 100 + SHIP_BUILD_MS);
  assert.equal(end.active, false); assert.deepEqual(end.scale, [1, 1, 1]);
  assert.equal(end.x, undefined); assert.equal(end.z, undefined); assert.equal(end.yaw, undefined);
});
test("movement arrival is distinct and finishes at the destination without a fabricated transit path", () => {
  const early = shipPose([1, 2], 0, cue("move"), 250);
  assert.equal(early.kind, "move"); assert.equal(early.active, true);
  assert.equal(shipPose([1, 2], 0, cue("move"), 100 + SHIP_MOVE_MS).active, false);
  assert.deepEqual(shipPose([1, 2], 0, cue("move"), 100 + SHIP_MOVE_MS).scale, [1, 1, 1]);
});
test("departure only shrinks/submerges at its original edge and expires", () => {
  const initial = shipDeparture(100, 100);
  assert.equal(initial.visible, true); assert.equal(Math.abs(initial.y), 0); assert.equal(initial.scale, 1);
  const midway = shipDeparture(100, 100 + SHIP_DEPART_MS / 2);
  assert(midway.visible && midway.y < 0 && midway.scale < 1);
  assert.equal(shipDeparture(100, 100 + SHIP_DEPART_MS).visible, false);
});
test("ambient rocking/bobbing stays bounded for a fleet and never changes planar anchors", () => {
  for (let i = 0; i < 2000; i++) {
    const pose = shipPose([i % 50, i % 50 + 1], i * .13);
    assert(Math.abs(pose.y) <= .008 && Math.abs(pose.pitch) <= .009 && Math.abs(pose.roll) <= .018);
    assert.deepEqual(pose.scale, [1, 1, 1]);
  }
});
test("static/reduced motion returns the exact identity visual even during an active cue", () => {
  for (const kind of ["build", "move"]) {
    const pose = shipPose([1, 2], 99, cue(kind), 110, false);
    assert.equal(pose.y, 0); assert.equal(pose.pitch, 0); assert.equal(pose.roll, 0);
    assert.deepEqual(pose.scale, [1, 1, 1]); assert.equal(pose.active, false);
  }
});
test("a completed/interrupted effect leaves exactly the ordinary pose without residual scale or tilt", () => {
  const normal = shipPose([1, 2], 3);
  for (const kind of ["build", "move"]) assert.deepEqual(shipPose([1, 2], 3, cue(kind), 10000), normal);
});
test("public preview uses real water edges, an owned anchor and an unoccupied movement target", () => {
  for (const large of [false, true]) {
    const state = publicShipFixture(large), source = state.legal.move_ship.sources[0], target = state.legal.ships[0];
    assert(source.some(v => target.includes(v) && state.occupied_v[v]?.[0] === 0));
    assert.equal(state.pirate_tile, null); assert.equal(state.occupied_ships[target.join(",")], undefined);
    for (const e of [source, target]) assert(state.edge_adj_hexes[e.join(",")].some(i => state.tiles[i].terrain === "sea"));
    assert.doesNotMatch(JSON.stringify(state), /assignment|recipe|seed|continuation|reward_ledger/);
  }
});
test("preview move changes only its public occupancy; repeated operation is a no-op", () => {
  const state = publicShipFixture(), before = JSON.stringify(state.tiles);
  const { source, target } = shipPreviewChange(state, true);
  assert.equal(state.occupied_ships[source.join(",")], undefined); assert.equal(state.occupied_ships[target.join(",")], 0);
  assert.equal(JSON.stringify(state.tiles), before); assert.equal(shipPreviewChange(state, true), null);
});
