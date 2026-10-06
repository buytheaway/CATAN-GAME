import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
const require = createRequire(import.meta.url);
const compiled = await build({ stdin: { contents: 'export {eventText} from "./GameEvents"; export {eventTransfers,liveEvents} from "./CardFlights";',
  resolveDir: fileURLToPath(new URL("../src/game/", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, format: "cjs", platform: "node", external: ["react", "react/jsx-runtime"] });
const loaded = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(require, loaded, loaded.exports);
const { eventText, eventTransfers, liveEvents } = loaded.exports;
const players = [{ pid: 0, name: "Alice" }, { pid: 1, name: "Bob" }, { pid: 2, name: "Cara" }];
const base = { id: 4, type: "theft", actor_pid: 0, victim_pid: 1, quantity: 1, tick: 3, at_ms: 1000 };

test("observer theft stays generic in both log and card flight; participants see the server face", () => {
  assert.equal(eventText(base, players), "Alice stole a resource from Bob");
  assert.deepEqual(eventTransfers(base).map(t => [t.from, t.to, t.resource]), [[1, 0, undefined]]);
  const personal = { ...base, resource: "brick" };
  assert.equal(eventText(personal, players), "Alice stole 1 brick from Bob");
  assert.equal(eventTransfers(personal)[0].resource, "brick");
  assert.equal(eventText({ ...base, type: "move_robber", tile: 0 }, players, [{ terrain: "hills", number: 6 }]),
    "Alice moved the robber to hills (6)");
  assert.equal(eventText({ ...base, type: "move_pirate", tile: 0 }, players, [{ terrain: "sea", number: null }]),
    "Alice moved the pirate to sea");
});

test("production uses only received exact own resources and generic opponent backs", () => {
  const event = Object.freeze({ ...base, type: "production", player_pid: 1, quantity: 3 });
  assert.deepEqual(eventTransfers(event).map(t => [t.from, t.to, t.resource, t.quantity]), [["bank", 1, undefined, 3]]);
  assert.equal(eventText(event, players), "Bob received 3 resource card(s)");
  const own = Object.freeze({ ...event, resources: Object.freeze({ wood: 2, wheat: 1 }) });
  assert.deepEqual(eventTransfers(own).map(t => [t.resource, t.quantity]), [["wood", 2], ["wheat", 1]]);
  assert.equal(eventText(own, players), "Bob received 2 wood, 1 wheat");
});

test("bank trade, purchase and discard flights represent already confirmed server transfers", () => {
  const event = { ...base, type: "trade_bank", paid: { wood: 4 }, gained: { ore: 1 }, quantity: 4 };
  assert.deepEqual(eventTransfers(event).map(t => [t.from, t.to, t.resource]), [[0, "bank", "wood"], ["bank", 0, "ore"]]);
  for (const type of ["buy_dev", "discard"]) {
    const generic = { ...base, type, quantity: 3 };
    assert.equal(eventTransfers(generic)[0].resource, undefined);
    assert.equal(eventTransfers(generic)[0].to, "bank");
  }
  assert.doesNotMatch(eventText({ ...base, type: "buy_dev" }, players), /knight|monopoly|victory/);
});

test("history on initial load, reconnect and rematch does not replay resource animations", () => {
  const events = [base];
  assert.deepEqual(liveEvents(null, "ROOM:1", true, events), []);
  assert.deepEqual(liveEvents({ key: "ROOM:1", last: 0, connected: false }, "ROOM:1", true, events), []);
  assert.deepEqual(liveEvents({ key: "ROOM:1", last: 0, connected: true }, "ROOM:2", true, events), []);
  assert.deepEqual(liveEvents({ key: "ROOM:1", last: 0, connected: true }, "ROOM:1", false, events), []);
});

test("duplicate and older snapshots do not animate again; one new event starts one transfer", () => {
  const previous = { key: "ROOM:1", last: 4, connected: true };
  assert.deepEqual(liveEvents(previous, "ROOM:1", true, [base]), []);
  assert.deepEqual(liveEvents(previous, "ROOM:1", true, [{ ...base, id: 3 }]), []);
  const next = { ...base, id: 5 };
  assert.deepEqual(liveEvents(previous, "ROOM:1", true, [base, next]), [next]);
});
