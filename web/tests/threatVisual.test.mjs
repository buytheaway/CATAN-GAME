import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";

const compiled = await build({ stdin: { contents: `export * from "./src/board/threatFeedback";
  export * from "./src/board3d/threatMotion"; export { TILE_TOP } from "./src/board3d/coordinates";`,
  resolveDir: fileURLToPath(new URL("../", import.meta.url)), loader: "tsx" }, bundle: true, write: false,
  format: "cjs", platform: "node", external: ["react"] });
const module = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  createRequire(import.meta.url), module, module.exports);
const { selectThreatEvents, advanceThreatFeedback: advance, threatPose, threatDeparture, theftPose, threatAnchor,
  threatCueKey, threatDuration, THREAT_MOVE_MS, THREAT_ENDPOINT_MS, THREAT_DEPART_MS, THEFT_MS, TILE_TOP } = module.exports;
const tiles = ["forest", "desert", "sea", "sea", "gold", "sea"].map((terrain, i) => ({ terrain, visibility: "revealed", center: [i * 58, 0] }));
const frame = (robbers = [0], pirate = 2, tick = 1, events = [], connected = true, key = "ROOM:1", publicTiles = tiles) =>
  ({ key, tick, connected, tiles: publicTiles, robbers, pirate, events, edgeAdjacency: { "0,1": [0, 1], "2,3": [2, 3] } });
const baseline = (robbers = [0], pirate = 2) => advance(null, frame(robbers, pirate)).baseline;
const move = (kind = "robber", from = 0, to = 1, id = 1, tick = 2, actor_pid = 0) =>
  ({ type: `move_${kind}`, from_tile: from, tile: to, id, tick, actor_pid });
const theft = (overrides = {}) => ({ type: "theft", id: 2, tick: 2, actor_pid: 0, victim_pid: 1, quantity: 1, ...overrides });
const cue = (kind = "robber", path = "adjacent", steal = false) => ({ kind, path, from: kind === "robber" ? 0 : 2,
  to: kind === "robber" ? 1 : 3, eventId: 1, theft: steal, started: 100 });
const close = (a, b) => assert(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test("initial hydration with movement/theft history establishes a quiet baseline", () => {
  assert.deepEqual(advance(null, frame([1], 3, 90, [move(), theft()])).changes, []);
});
test("one adjacent accepted robber movement needs exact old/new positions and public evidence", () => {
  assert.deepEqual(advance(baseline(), frame([1], 2, 2, [move()])).changes,
    [{ kind: "robber", from: 0, to: 1, path: "adjacent", eventId: 1, theft: false }]);
});
test("accepted pirate movement uses the shared public sea edge with owner zero as a valid actor", () => {
  const result = advance(baseline(), frame([0], 3, 2, [move("pirate", 2, 3)]));
  assert.equal(result.changes[0].kind, "pirate"); assert.equal(result.changes[0].path, "adjacent");
});
test("a canonical inactive robber sentinel does not suppress known pirate movement", () => {
  const result = advance(baseline([-1]), frame([-1], 3, 2, [move("pirate", 2, 3)]));
  assert.equal(result.baseline.validFigures, true);
  assert.deepEqual(result.changes, [{ kind: "pirate", from: 2, to: 3, path: "adjacent", eventId: 1, theft: false }]);
  assert.deepEqual(advance(baseline([-1]), frame([0], 2, 2, [move("robber", -1, 0)])).changes, []);
});
test("a canonical offboard robber can show only a confirmed public theft card at its known destination", () => {
  const events = [move("robber", -1, 1), theft()];
  const result = advance(baseline([-1]), frame([1], 2, 2, events));
  assert.deepEqual(result.changes, [{ kind: "robber", from: -1, to: 1, path: "snap", eventId: 1, theft: true }]);
  const effect = { ...result.changes[0], started: 100 };
  assert.equal(threatDuration(effect), THEFT_MS);
  for (const now of [100, 200, 500, 100 + THEFT_MS]) {
    const pose = threatPose("robber", [99, 0, 99], [1, 0, 0], effect, now);
    assert.deepEqual(pose.position, [0, 0, 0]); assert.equal(pose.scale, 1);
    assert.equal(pose.moving, false); assert.equal(pose.arriving, false); assert.equal(pose.active, false);
  }
  assert.deepEqual(advance(baseline([-1]), frame([1], 2, 2, [events[0]])).changes, []);
});
test("card-only offboard theft still rejects hidden destinations, missing evidence, ambiguity and private inputs", () => {
  const hidden = tiles.map((tile, i) => i === 1 ? { visibility: "hidden", terrain: "fog" } : tile);
  const events = [move("robber", -1, 1), theft()];
  const beforeHidden = advance(null, frame([-1], 2, 1, [], true, "ROOM:1", hidden)).baseline;
  assert.deepEqual(advance(beforeHidden, frame([1], 2, 2, events)).changes, []);
  assert.deepEqual(advance(baseline([-1]), frame([1], 2, 2, events, true, "ROOM:1", hidden)).changes, []);
  for (const evidence of [[theft()], [move("robber", 0, 1), theft()], [events[0], theft({ quantity: 2 })], [events[0], theft(), theft()]])
    assert.deepEqual(advance(baseline([-1]), frame([1], 2, 2, evidence)).changes, []);
  for (const event of events) Object.defineProperty(event, "resource", { enumerable: true, get() { throw Error("Private offboard theft read"); } });
  assert.equal(advance(baseline([-1]), frame([1], 2, 2, selectThreatEvents(events))).changes[0].path, "snap");
});
test("known distant endpoints get endpoint effects without a fabricated route", () => {
  for (const [kind, from, to, robbers, pirate] of [["robber", 0, 4, [4], 2], ["pirate", 2, 5, [0], 5]]) {
    const result = advance(baseline(), frame(robbers, pirate, 2, [move(kind, from, to)]));
    assert.equal(result.changes[0].path, "endpoints");
  }
});
test("missing, mismatched, wrong-kind, wrong-tick or multiple movement events never identify a move", () => {
  for (const events of [[], [move("robber", 4, 1)], [move("robber", 0, 4)], [move("pirate", 0, 1)],
    [move("robber", 0, 1, 1, 1)], [move(), move("robber", 0, 1, 2)], [move(), move()],
    [{ ...move(), id: NaN }], [{ ...move(), actor_pid: -1 }]])
    assert.deepEqual(advance(baseline(), frame([1], 2, 2, events)).changes, []);
});
test("an event or theft without changed authoritative positions never creates movement or stealing feedback", () => {
  for (const events of [[move()], [theft()], [move(), theft()]]) assert.deepEqual(advance(baseline(), frame([0], 2, 2, events)).changes, []);
});
test("unknown endpoints, previously unknown endpoints and inappropriate land/sea categories snap", () => {
  const hidden = tiles.map((tile, i) => i === 1 ? { terrain: "fog", visibility: "hidden" } : tile);
  assert.deepEqual(advance(baseline(), frame([1], 2, 2, [move()], true, "ROOM:1", hidden)).changes, []);
  const beforeHidden = advance(null, frame([0], 2, 1, [], true, "ROOM:1", hidden)).baseline;
  assert.deepEqual(advance(beforeHidden, frame([1], 2, 2, [move()])).changes, []);
  assert.deepEqual(advance(baseline(), frame([2], 2, 2, [move("robber", 0, 2)])).changes, []);
  assert.deepEqual(advance(baseline(), frame([0], 1, 2, [move("pirate", 2, 1)])).changes, []);
});
test("hidden terrain and number getters are never read to classify public movement", () => {
  const hidden = { visibility: "hidden" };
  for (const key of ["terrain", "number", "assignment", "resource"]) Object.defineProperty(hidden, key, { get() { throw Error("Hidden read"); } });
  const publicTiles = [...tiles, hidden];
  assert.equal(advance(null, frame([0], 2, 1, [], true, "ROOM:1", publicTiles)).baseline.known.size, tiles.length);
  const numbered = tiles.map(tile => Object.defineProperty({ ...tile }, "number", { get() { throw Error("Unused token read"); } }));
  const before = advance(null, frame([0], 2, 1, [], true, "ROOM:1", numbered)).baseline;
  assert.equal(advance(before, frame([1], 2, 2, [move()], true, "ROOM:1", numbered)).changes.length, 1);
});
test("offboard figure changes and malformed/duplicated figure arrays never invent an identity", () => {
  for (const [robbers, pirate, event] of [[[1, 1], 2, move()], [[99], 2, move("robber", 0, 99)],
    [[0], null, move("pirate", 2, null)], [[], 2, move("robber", 0, 1)]])
    assert.deepEqual(advance(baseline(), frame(robbers, pirate, 2, [event])).changes, []);
  const offboard = advance(null, frame([-1], null)).baseline;
  assert.deepEqual(advance(offboard, frame([0], null, 2, [move("robber", -1, 0)])).changes, []);
});
test("multiple robbers allow only one unambiguous removed/added pair, never guessed matching", () => {
  assert.equal(advance(baseline([0, 4]), frame([1, 4], 2, 2, [move()])).changes.length, 1);
  assert.deepEqual(advance(baseline([0, 4]), frame([1, 5], 2, 2, [move()])).changes, []);
  assert.deepEqual(advance(baseline(), frame([1], 3, 2, [move(), move("pirate", 2, 3, 2)])).changes, []);
});
test("duplicate, stale, rejected/equal and invalid ticks preserve the current baseline", () => {
  const before = baseline();
  for (const tick of [1, 0, -1, NaN, Infinity, 1.5]) {
    const result = advance(before, frame([1], 2, tick, [move()]));
    assert.equal(result.baseline, before); assert.deepEqual(result.changes, []);
  }
});
test("gaps consume a quiet baseline and a previously observed move ID cannot replay", () => {
  const gap = advance(baseline(), frame([1], 2, 5, [move("robber", 0, 1, 7, 5)])); assert.deepEqual(gap.changes, []);
  assert.deepEqual(advance(gap.baseline, frame([0], 2, 6, [move("robber", 1, 0, 7, 6)])).changes, []);
  assert.equal(advance(gap.baseline, frame([0], 2, 6, [move("robber", 1, 0, 8, 6)])).changes.length, 1);
});
test("cached reconnect uses raw tiles identity and consumes the first fresh same-tick snapshot quietly", () => {
  const offline = advance(baseline(), frame([0], 2, 1, [], false)).baseline;
  const cached = advance(offline, frame([0], 2)).baseline; assert.equal(cached.awaitingFresh, true);
  const fresh = advance(cached, frame([0], 2, 1, [], true, "ROOM:1", [...tiles]));
  assert.equal(fresh.baseline.awaitingFresh, false); assert.deepEqual(fresh.changes, []);
  assert.equal(advance(fresh.baseline, frame([1], 2, 2, [move()])).changes.length, 1);
});
test("offline committed movement, new room and rematch restore final figures without historical effects", () => {
  const offline = advance(baseline(), frame([0], 2, 1, [], false)).baseline;
  assert.deepEqual(advance(offline, frame([1], 2, 2, [move(), theft()], true, "ROOM:1", [...tiles])).changes, []);
  for (const key of ["ROOM:2", "OTHER:1"]) assert.deepEqual(advance(baseline(), frame([1], 2, 2, [move()], true, key)).changes, []);
});
test("static/SVG observation consumes fresh movement so re-enabling does not replay it", () => {
  const next = advance(baseline(), frame([1], 2, 2, [move(), theft()])).baseline;
  assert.deepEqual(advance(next, frame([1], 2, 2, [move(), theft()])).changes, []);
});
test("theft needs one fresh same-actor same-tick public quantity-one event after its matching move", () => {
  assert.equal(advance(baseline(), frame([1], 2, 2, [move(), theft()])).changes[0].theft, true);
  assert.equal(advance(baseline(), frame([1], 2, 2, [move("robber", 0, 1, 1, 2, 1), theft({ actor_pid: 1, victim_pid: 0 })])).changes[0].theft, true);
  for (const events of [[move()], [move(), theft({ quantity: 0 })], [move(), theft({ quantity: 2 })], [move(), theft({ quantity: "1" })],
    [move(), theft({ actor_pid: 2 })], [move(), theft({ victim_pid: 0 })], [move(), theft({ victim_pid: -1 })], [move(), theft({ victim_pid: undefined })],
    [move(), theft({ tick: 1 })], [move(), theft({ id: 1 })], [move(), theft(), theft()], [move(), theft(), theft({ id: 3 })]])
    assert.equal(advance(baseline(), frame([1], 2, 2, events)).changes[0].theft, false);
});
test("closed event projection never reads or spreads private fields even for entitled participants", () => {
  const input = [move(), theft(), { type: "production", id: 3, tick: 2, actor_pid: 1 }];
  for (const event of input) for (const key of ["resource", "resources", "paid", "gained", "res", "dev_cards", "vp", "_private"])
    Object.defineProperty(event, key, { enumerable: true, get() { throw Error("Private field read: " + key); } });
  const selected = selectThreatEvents(input);
  assert.deepEqual(selected, [move(), theft()]); assert.notEqual(selected[0], input[0]);
  const publicFrame = frame([1], 2, 2, selected);
  for (const key of ["players", "res", "dev_cards", "resources", "assignment", "cmd", "ack"])
    Object.defineProperty(publicFrame, key, { enumerable: true, get() { throw Error("Unexpected frame field read: " + key); } });
  assert.equal(advance(baseline(), publicFrame).changes[0].theft, true);
});
test("different entitled stolen-resource payloads produce identical public cues and neutral card poses", () => {
  const results = ["wood", "ore", undefined].map(resource => advance(baseline(), frame([1], 2, 2,
    selectThreatEvents([move(), { ...theft(), resource, resources: { [resource]: 99 }, dev_cards: ["knight"] }]))).changes);
  assert.deepEqual(results[0], results[1]); assert.deepEqual(results[1], results[2]);
  assert.equal(JSON.stringify(results).includes("resource"), false);
});
test("exact final offsets and pirate yaw compensation preserve both adjacent world endpoints", () => {
  const from = [2, 0, -1], to = [-3, 0, 4];
  assert.deepEqual(threatAnchor("robber", to), [-2.52, TILE_TOP, 4.1]);
  assert.deepEqual(threatAnchor("pirate", to), [-2.85, TILE_TOP + .03, 4.24]);
  for (const kind of ["robber", "pirate"]) {
    const pose = threatPose(kind, from, to, cue(kind), 100, 0), yaw = kind === "pirate" ? -.3 : 0;
    const worldX = pose.position[0] * Math.cos(yaw) + pose.position[2] * Math.sin(yaw);
    const worldZ = -pose.position[0] * Math.sin(yaw) + pose.position[2] * Math.cos(yaw);
    close(worldX + to[0], from[0]); close(worldZ + to[2], from[2]);
    const end = threatPose(kind, from, to, cue(kind), 100 + THREAT_MOVE_MS, 0, false);
    assert.deepEqual(end.position, [0, 0, 0]); assert.equal(end.scale, 1); assert.equal(end.active, false);
  }
});
test("adjacent movement lifts then arrives; endpoint-only motion never interpolates planar coordinates", () => {
  const from = [0, 0, 0], to = [9, 0, 9];
  const moving = threatPose("robber", from, to, cue(), 100 + THREAT_MOVE_MS / 2);
  assert(moving.position[1] > .2); assert.equal(moving.moving, true);
  assert.equal(threatPose("robber", from, to, cue(), 100 + THREAT_MOVE_MS * .9).arriving, true);
  for (let elapsed = 0; elapsed <= THREAT_ENDPOINT_MS; elapsed += 17) {
    const pose = threatPose("robber", from, to, cue("robber", "endpoints"), 100 + elapsed);
    assert.equal(pose.position[0], 0); assert.equal(pose.position[2], 0); assert.equal(pose.moving, false);
  }
});
test("departure and neutral theft are finite, bounded and cease drawing at their deadlines", () => {
  assert.equal(threatDeparture(100, 100).visible, true); assert.equal(threatDeparture(100, 100 + THREAT_DEPART_MS).visible, false);
  assert.equal(theftPose(100, 100 + THEFT_MS).visible, false);
  for (let t = 0; t <= 1; t += .01) {
    const card = theftPose(100, 100 + t * THEFT_MS);
    assert(card.scale >= 0 && card.scale <= 1); assert(Math.abs(card.position[0]) <= .18);
    assert(card.position[1] >= .95 && card.position[1] <= 1.17);
  }
  assert.equal(threatDuration(cue("robber", "adjacent", true)), Math.max(THREAT_MOVE_MS, THEFT_MS));
});
test("pirate rocking is bounded, uses only local transforms and becomes exact identity in Still", () => {
  const position = [1, 0, 1];
  for (let i = 0; i < 1000; i++) {
    const pose = threatPose("pirate", position, position, undefined, Infinity, i * .1);
    assert(Math.abs(pose.position[1]) <= .004 && Math.abs(pose.pitch) <= .006 && Math.abs(pose.roll) <= .012);
    assert.equal(pose.position[0], 0); assert.equal(pose.position[2], 0); assert.equal(pose.scale, 1); assert.equal(pose.active, false);
  }
  const pose = threatPose("pirate", position, position, cue("pirate"), 110, 99, false);
  assert.deepEqual(pose.position, [0, 0, 0]); assert.equal(pose.pitch, 0); assert.equal(pose.roll, 0); assert.equal(pose.scale, 1);
  assert.equal(threatDeparture(100, 110, false).visible, false); assert.equal(theftPose(100, 110, false).visible, false);
});
test("rapid accepted actions replace old figure destinations while unchanged figures stay quiet", () => {
  const first = advance(baseline(), frame([1], 2, 2, [move(), theft()]));
  const second = advance(first.baseline, frame([1], 3, 3, [move(), theft(), move("pirate", 2, 3, 3, 3)]));
  assert.equal(second.changes.length, 1); assert.equal(second.changes[0].kind, "pirate");
  const third = advance(second.baseline, frame([0], 3, 4, [move("robber", 1, 0, 4, 4)]));
  assert.equal(third.changes[0].to, 0); assert.equal(threatCueKey("robber", 0), "robber:0");
});
