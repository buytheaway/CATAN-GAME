import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";

const compiled = await build({ stdin: { contents: `export * from "./src/board3d/pieceFeedback";`,
  resolveDir: fileURLToPath(new URL("../", import.meta.url)), loader: "tsx" }, bundle: true, write: false,
  format: "cjs", platform: "node", external: ["react"] });
const module = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  createRequire(import.meta.url), module, module.exports);
const { advancePieceFeedback: advance, piecePose, upgradeEchoPose, pieceDuration,
  ROAD_BUILD_MS, SETTLEMENT_BUILD_MS, CITY_UPGRADE_MS, CITY_ECHO_MS } = module.exports;
const frame = (roads = {}, vertices = {}, tick = 1, connected = true, key = "ROOM:1") => ({ key, tick, connected, roads, vertices });
const baseline = (roads = {}, vertices = {}) => advance(null, frame(roads, vertices)).baseline;
const cue = kind => ({ kind, owner: 0, started: 100 });

test("hydrated roads, settlements and cities establish a quiet public baseline", () => {
  const result = advance(null, frame({ "0,1": 0 }, { 0: [0, 1], 1: [1, 2] }, 50));
  assert.deepEqual(result.changes, []); assert.equal(result.baseline.pieces.size, 3);
});
test("adjacent accepted road and settlement additions retain their public identity and owner zero", () => {
  assert.deepEqual(advance(baseline(), frame({ "0,1": 0 }, { 2: [1, 1] }, 2)).changes,
    [{ id: "e:0,1", owner: 0, kind: "road" }, { id: "v:2", owner: 1, kind: "settlement" }]);
});
test("a same-owner explicit settlement-to-city transition identifies an upgrade", () => {
  assert.deepEqual(advance(baseline({}, { 3: [0, 1] }), frame({}, { 3: [0, 2] }, 2)).changes,
    [{ id: "v:3", owner: 0, kind: "upgrade" }]);
});
test("an initially added city never invents a historical settlement or upgrade", () => {
  const result = advance(baseline(), frame({}, { 3: [0, 2] }, 2));
  assert.deepEqual(result.changes, []); assert.equal(result.baseline.pieces.get("v:3"), "0:2");
});
test("owner replacement, downgrade and removal snap without construction or an upgrade echo", () => {
  for (const [before, after] of [[{ 3: [0, 1] }, { 3: [1, 2] }], [{ 3: [0, 1] }, { 3: [1, 1] }],
    [{ 3: [0, 2] }, { 3: [0, 1] }], [{ 3: [0, 1] }, {}]])
    assert.deepEqual(advance(baseline({}, before), frame({}, after, 2)).changes, []);
  assert.deepEqual(advance(baseline({ "0,1": 0 }), frame({ "0,1": 1 }, {}, 2)).changes, []);
});
test("ambiguous mixed frames do not animate an unrelated addition as a guessed construction", () => {
  assert.deepEqual(advance(baseline({ "0,1": 0 }), frame({ "1,2": 0 }, { 3: [0, 1] }, 2)).changes, []);
  assert.deepEqual(advance(baseline(), frame({ "0,1": 0 }, { 3: [0, 2] }, 2)).changes, []);
});
test("duplicates, equal/rejected and stale frames preserve the baseline without feedback", () => {
  const previous = baseline();
  for (const tick of [1, 0, -1, NaN, Infinity, 1.5]) {
    const result = advance(previous, frame({ "0,1": 0 }, {}, tick));
    assert.deepEqual(result.changes, []); assert.equal(result.baseline, previous);
  }
});
test("coalesced tick gaps snap to current occupancy then allow the next adjacent construction", () => {
  const gap = advance(baseline(), frame({ "0,1": 0 }, { 3: [0, 2] }, 5));
  assert.deepEqual(gap.changes, []);
  assert.deepEqual(advance(gap.baseline, frame({ "0,1": 0, "1,2": 1 }, { 3: [0, 2] }, 6)).changes,
    [{ id: "e:1,2", owner: 1, kind: "road" }]);
});
test("disconnect, cached reconnect and first fresh occupancy suppress offline construction", () => {
  const roads = { "0,1": 0 }, vertices = { 3: [0, 1] };
  let previous = advance(null, frame(roads, vertices)).baseline;
  previous = advance(previous, frame(roads, vertices, 1, false)).baseline;
  previous = advance(previous, frame(roads, vertices)).baseline; assert.equal(previous.awaitingFresh, true);
  const fresh = advance(previous, frame({ ...roads, "1,2": 0 }, { 3: [0, 2] }, 2));
  assert.equal(fresh.baseline.awaitingFresh, false); assert.deepEqual(fresh.changes, []);
  assert.equal(advance(fresh.baseline, frame({ ...fresh.baseline.roads, "2,3": 0 }, fresh.baseline.vertices, 3)).changes.length, 1);
});
test("a fresh same-tick reconnect object establishes a baseline before the following real action", () => {
  const roads = {}, vertices = {};
  const offline = advance(baseline(), frame(roads, vertices, 1, false)).baseline;
  const fresh = advance(offline, frame({}, {}, 1)).baseline; assert.equal(fresh.awaitingFresh, false);
  assert.equal(advance(fresh, frame({}, { 3: [0, 1] }, 2)).changes[0].kind, "settlement");
});
test("new match and room scopes cannot reuse historical edge/vertex identities", () => {
  for (const key of ["ROOM:2", "OTHER:1"]) assert.deepEqual(advance(baseline(), frame({ "0,1": 0 }, { 3: [0, 2] }, 2, true, key)).changes, []);
});
test("malformed public occupancy never supplies animation identities", () => {
  const result = advance(baseline(), frame({ bad: 0, "1,0": 0, "0,0": 0, "1,2": -1, "2,3": undefined },
    { bad: [0, 1], 1: [-1, 1], 2: [0, 3], 3: [0, 1, 2], 4: undefined, 5: [0.5, 1] }, 2));
  assert.deepEqual(result.changes, []);
});
test("only the two public occupancy objects are read; terrain, events, rules, hands and intent are irrelevant", () => {
  const input = frame(Object.freeze({ "0,1": 0 }), Object.freeze({ 3: Object.freeze([0, 1]) }), 2);
  for (const key of ["tiles", "res", "players", "rules", "events", "assignment", "cmd", "ack"])
    Object.defineProperty(input, key, { enumerable: true, get() { throw Error("Unexpected field read: " + key); } });
  const before = baseline(); assert.equal(advance(before, input).changes.length, 2); assert.equal(before.pieces.size, 0);
});
test("multiple constructions and rapid adjacent actions keep distinct road, settlement and upgrade identities", () => {
  const first = advance(baseline(), frame({ "0,1": 0, "1,2": 1 }, { 3: [0, 1], 4: [1, 1] }, 2));
  assert.equal(first.changes.length, 4);
  const next = advance(first.baseline, frame({ "0,1": 0, "1,2": 1, "2,3": 0 }, { 3: [0, 2], 4: [1, 1] }, 3));
  assert.deepEqual(next.changes.map(c => [c.id, c.kind]), [["e:2,3", "road"], ["v:3", "upgrade"]]);
  assert.deepEqual(advance(next.baseline, frame(next.baseline.roads, next.baseline.vertices, 4)).changes, []);
});
test("quiet static/SVG observation consumes placements so re-enabling cannot rediscover history", () => {
  let previous = baseline();
  previous = advance(previous, frame({ "0,1": 0 }, { 3: [0, 1] }, 2)).baseline;
  previous = advance(previous, frame({ "0,1": 0 }, { 3: [0, 2] }, 3)).baseline;
  assert.deepEqual(advance(previous, frame({ "0,1": 0 }, { 3: [0, 2] }, 3)).changes, []);
});
test("road construction grows along local X without planar movement, yaw or scale overshoot", () => {
  const start = piecePose(cue("road"), 100), middle = piecePose(cue("road"), 100 + ROAD_BUILD_MS / 2);
  assert(start.scale[0] < middle.scale[0] && middle.scale[0] < 1); assert.equal(start.y, 0); assert.equal(start.scale[2], 1);
  for (const name of ["x", "z", "rotation", "yaw"]) assert.equal(start[name], undefined);
});
test("settlement emergence is brief, bounded and distinct from the city upgrade foundation", () => {
  const settlement = piecePose(cue("settlement"), 100), city = piecePose(cue("upgrade"), 100);
  assert(settlement.y < -.1 && settlement.scale[1] < .4); assert(city.y > settlement.y && city.scale[1] > settlement.scale[1]);
  assert.equal(settlement.kind, "settlement"); assert.equal(city.kind, "upgrade");
  assert.deepEqual(piecePose(cue("upgrade"), 210).scale, city.scale);
});
test("upgrade echo shrinks only at the same vertex and disappears while the city continues emerging", () => {
  const start = upgradeEchoPose(cue("upgrade"), 100), middle = upgradeEchoPose(cue("upgrade"), 100 + CITY_ECHO_MS / 2);
  assert.equal(start.visible, true); assert.equal(start.scale, 1); assert(middle.scale < 1 && middle.y < 0);
  assert.equal(upgradeEchoPose(cue("upgrade"), 100 + CITY_ECHO_MS).visible, false);
  assert.equal(piecePose(cue("upgrade"), 100 + CITY_ECHO_MS).active, true);
  assert.equal(upgradeEchoPose(cue("settlement"), 100).visible, false);
});
test("all finite construction poses finish exactly at identity without residual height, scale or tilt", () => {
  for (const kind of ["road", "settlement", "upgrade"]) {
    for (let t = 0; t < 1; t += .03) {
      const pose = piecePose(cue(kind), 100 + t * pieceDuration(kind));
      assert(pose.scale.every(value => value > 0 && value <= 1)); assert(pose.y >= -.12 && pose.y <= 0);
    }
    assert.deepEqual(piecePose(cue(kind), 100 + pieceDuration(kind)), piecePose());
    assert.deepEqual(piecePose(cue(kind), 10000), piecePose());
  }
});
test("static/reduced motion restores the exact final pose and suppresses the upgrade echo immediately", () => {
  for (const kind of ["road", "settlement", "upgrade"]) assert.deepEqual(piecePose(cue(kind), 110, false), piecePose());
  assert.equal(upgradeEchoPose(cue("upgrade"), 110, false).visible, false);
  assert(ROAD_BUILD_MS < SETTLEMENT_BUILD_MS && SETTLEMENT_BUILD_MS < CITY_UPGRADE_MS && CITY_ECHO_MS < CITY_UPGRADE_MS);
});
