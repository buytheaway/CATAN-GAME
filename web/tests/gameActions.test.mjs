import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
const compiled = await build({ stdin: { contents: 'export * from "./actions"; export * from "./costs"; export {contextPrompt} from "./presentation";',
  resolveDir: fileURLToPath(new URL("../src/game/", import.meta.url)), loader: "ts" }, bundle: true, write: false, platform: "node", format: "esm" });
const ui = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);
function state(overrides = {}) {
  return { phase: "main", turn: 0, rolled: true, pending_action: null, game_over: false,
    occupied_v: { "12": [0, 1], "17": [1, 2] }, ports: [],
    bank_available: { wood: true, brick: true, sheep: true, wheat: true, ore: true },
    dev_played_turn: { "0": false }, free_roads: { "0": 0 },
    players: [{ pid: 0, name: "Alice", vp: 3, res: { wood: 5, brick: 2, sheep: 1, wheat: 1, ore: 1 },
      dev_cards: [{ type: "knight", new: false }, { type: "knight", new: true }] },
    { pid: 1, name: "Bob", vp: 2, resource_count: 9, dev_count: 3 }], ...overrides };
}
test("displayed maritime ratio uses only owned port endpoints, best resource ratio and original snapshot", () => {
  const s = state({ ports: [[[12, 13], "3:1"], [[11, 12], "2:1:wood"], [[17, 18], "2:1:ore"]] });
  const before = JSON.stringify(s);
  assert.equal(ui.maritimeRate(s, 0, "wood"), 2);assert.equal(ui.maritimeRate(s, 0, "ore"), 3);
  assert.equal(ui.maritimeRate(s, 1, "ore"), 2);assert.equal(ui.maritimeRate(s, 1, "wood"), 4);
  assert.equal(JSON.stringify(s), before);
});

test("hand clicks create a local trade draft, cap Give at actual own counts and preserve the snapshot", () => {
  const hand = Object.freeze({ wood: 2, brick: 1 });
  const first = ui.addHandResource(null, "wood", hand);
  assert.deepEqual(first, { give: { wood: 1 }, want: {}, target: "everyone" });
  const second = ui.addHandResource(first, "wood", hand);
  assert.deepEqual(ui.addHandResource(second, "wood", hand).give, { wood: 2 });
  const both = ui.addHandResource({ ...second, target: "1", want: { ore: 2 } }, "brick", hand);
  assert.deepEqual(both, { give: { wood: 2, brick: 1 }, want: { ore: 2 }, target: "1" });
  assert.deepEqual(ui.changeResource(both.give, "brick", -1), { wood: 2 });
  assert.deepEqual(ui.changeResource({}, "ore", -1), {});
  assert.deepEqual(first.give, { wood: 1 }); assert.deepEqual(hand, { wood: 2, brick: 1 });
});

test("bank draft accepts exact 4/3/2 ratios and multi-card batches but rejects malformed combinations", () => {
  for (const [rate, ports] of [[4, []], [3, [[[12, 13], "3:1"]]], [2, [[[12, 13], "2:1:wood"]]]]) {
    const s = state({ ports }); s.players[0].res.wood = 12;
    const draft = { target: "bank", give: { wood: rate * 2 }, want: { ore: 2 } };
    assert.equal(ui.bankDraftReason(s, 0, draft), null);
    assert.deepEqual(ui.bankDraftCommand(draft), { type: "trade_bank", give: "wood", get: "ore", get_qty: 2 });
    for (const change of [{ give: {} }, { want: {} }, { give: { wood: rate + 1 } }, { want: { wood: 2 } },
      { give: { wood: rate, sheep: 1 } }, { want: { ore: 1, sheep: 1 } }])
      assert.ok(ui.bankDraftReason(s, 0, { ...draft, ...change }));
    s.players[0].res.wood = 0; assert.ok(ui.bankDraftReason(s, 0, draft));
  }
});

test("central preview uses complete quantities and never uses opponents' resources or hides missing costs", () => {
  assert.deepEqual(ui.costPreview("city", { wheat: 2, ore: 2 }), [
    { resource: "wheat", quantity: 2, available: true }, { resource: "ore", quantity: 3, available: false }]);
  assert.deepEqual(ui.costPreview("road", {}, true), []);
  assert.deepEqual(ui.ACTION_COSTS.ship, { wood: 1, sheep: 1 });
  assert.deepEqual(ui.ACTION_COSTS.dev, { sheep: 1, wheat: 1, ore: 1 });
});
test("bank form gates turn/roll/pending, same resource, own hand and public availability", () => {
  assert.equal(ui.bankTradeReason(state(), 0, "wood", "ore"), null);
  for (const override of [{ turn: 1 }, { rolled: false }, { pending_action: "robber_move" }, { game_over: true },
    { bank_available: { ore: false } }]) assert.ok(ui.bankTradeReason(state(override), 0, "wood", "ore"));
  assert.ok(ui.bankTradeReason(state(), 0, "ore", "wood"));
  assert.ok(ui.bankTradeReason(state(), 0, "wood", "wood"));
});
test("offer creation requires cards on both sides and never assumes resources of a target", () => {
  const s = state();assert.equal(ui.offerCreateReason(s, 0, { wood: 2 }, { ore: 1 }), null);
  for (const give of [{}, { wood: 6 }, { wood: -1 }, { wood: 1.5 }]) assert.ok(ui.offerCreateReason(s, 0, give, { ore: 1 }));
  assert.ok(ui.offerCreateReason(s, 0, { wood: 1 }, {}));
  assert.deepEqual(ui.resourcePayload({ wood: 2, brick: 0 }), { wood: 2 });
});
test("offer audience and off-turn response use existing public terms plus recipient's own hand", () => {
  const offers = [1, 2, 3].map((id, i) => ({ offer_id: id, from_pid: 0, to_pid: [null, 1, 2][i],
    give: { wood: 2 }, get: { ore: 1 }, status: "active" }));
  const s = state({ trade_offers: offers });
  assert.deepEqual(ui.addressedOffers(s, 1).map(o => o.offer_id), [1, 2]);
  assert.ok(ui.offerResponseReason(s, 1, offers[0], true));
  assert.equal(ui.offerResponseReason(s, 1, offers[0], false), null);
  s.players[1].res = { ore: 1 };assert.equal(ui.offerResponseReason(s, 1, offers[0], true), null);
  assert.ok(ui.offerResponseReason(s, 1, offers[2], false));
  assert.ok(ui.offerResponseReason({ ...s, turn: 1 }, 1, offers[0], true));
});
test("private dev hand aggregates self only, distinguishes new cards and never reads other hands", () => {
  const s = state();s.players[1].dev_cards = [{ type: "monopoly", new: false }];
  assert.deepEqual(ui.devHand(s, 0).map(c => [c.type, c.count, c.fresh]), [["knight", 2, 1]]);
  assert.equal(ui.devHand(s, 2).length, 0);
});
test("dev play permits an older card before Roll but blocks new/passive/pending/already-played cases", () => {
  assert.equal(ui.devPlayReason(state({ rolled: false }), 0, "knight"), null);
  for (const override of [{ dev_played_turn: { "0": true } }, { dev_played_turn: undefined }, { turn: 1 },
    { phase: "setup" }, { pending_action: "discard" }, { game_over: true }]) assert.ok(ui.devPlayReason(state(override), 0, "knight"));
  const s = state();s.players[0].dev_cards = [{ type: "knight", new: true }];
  assert.ok(ui.devPlayReason(s, 0, "knight"));assert.ok(ui.devPlayReason(state(), 0, "victory_point"));
});
test("purchase requires own cost/roll but playing earlier in the turn does not block buying", () => {
  assert.equal(ui.buyDevReason(state({ dev_played_turn: { "0": true } }), 0), null);
  assert.ok(ui.buyDevReason(state({ rolled: false }), 0));
  const s = state();s.players[0].res.ore = 0;assert.ok(ui.buyDevReason(s, 0));
});
test("Year of Plenty creates exact existing two-resource payload and respects bank booleans without exact counts", () => {
  const s = state();s.players[0].dev_cards = [{ type: "year_of_plenty", new: false }];
  assert.equal(ui.plentyReason(s, 0, { wood: 2 }), null); // A one-card bank remainder can only be rejected by the server.
  assert.deepEqual(ui.plentyCommand({ wood: 2 }), { type: "play_dev", card: "year_of_plenty", a: "wood", qa: 2, b: "", qb: 0 });
  assert.deepEqual(ui.plentyCommand({ sheep: 1, ore: 1 }), { type: "play_dev", card: "year_of_plenty", a: "sheep", qa: 1, b: "ore", qb: 1 });
  for (const choice of [{}, { wood: 1 }, { wood: 3 }, { wood: 1.5, ore: .5 }]) assert.ok(ui.plentyReason(s, 0, choice));
  s.bank_available.wood = false;assert.ok(ui.plentyReason(s, 0, { wood: 2 }));
});
test("Road Building prompt advances from personal free-road snapshot and never decrements it locally", () => {
  const interaction = { action: "road", selection: {}, legal: { road_free: true, roads: [[1, 2]] } };
  for (const [left, step] of [[2, 1], [1, 2]]) {
    const s = state({ free_roads: { "0": left } });const before = JSON.stringify(s);
    assert.equal(ui.contextPrompt(s, 0, interaction).title, `Place road ${step} of 2`);
    assert.equal(JSON.stringify(s), before);
  }
});
test("results honor server winner and rematch hint handles disconnected host without remapping IDs", () => {
  const s = state({ game_over: true, winner_pid: 1 });s.players[0].vp = 11;s.players[1].vp = 10;
  assert.equal(ui.finalStandings(s)[0].pid, 1);assert.equal(s.players[0].pid, 0);
  const room = { host_pid: 0, players: [{ pid: 0, name: "Alice", connected: false },
    { pid: 1, name: "Bob", connected: true }, { pid: 2, name: "Cara", connected: true }] };
  assert.equal(ui.rematchReason(room, 1, true), null);
  assert.ok(ui.rematchReason(room, 2, true));assert.ok(ui.rematchReason(room, 1, false));
  room.players[2].connected = false;assert.ok(ui.rematchReason(room, 1, true));
});
