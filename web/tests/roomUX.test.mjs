import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";

const require = createRequire(import.meta.url);
const compiled = await build({
  stdin: { contents: `export * from "./components/RoomSettings";
    export {default as RoomChat} from "./game/RoomChat";
    export {default as TurnTimer,timerSeconds} from "./game/TurnTimer";
    export * from "./board/colors"; export * from "./game/GameHUD";`,
    resolveDir: fileURLToPath(new URL("../src", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  external: ["react", "react/jsx-runtime"],
  loader: { ".css": "empty" },
});
let elements = [];
const traced = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (typeof type === "string") elements.push({ ...props, type });
  return jsxRuntime[name](type, props, key);
}])) };
const loaded = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  name => name === "react/jsx-runtime" ? traced : require(name), loaded, loaded.exports);
const { MatchSettings, PlayerColors, RoomChat, TurnTimer, timerSeconds, colorForPlayer, ROOM_COLORS, BankSummary, GameTopBar } = loaded.exports;
function render(Component, props) {
  elements = [];
  const html = renderToStaticMarkup(React.createElement(Component, props));
  return { html, elements };
}
const settings = { dice_mode: "balanced", starting_player: "host", turn_timer: 60, bank_visibility: "visible", target_vp: 12 };
const room = { host_pid: 0, status: "lobby", settings, players: [
  { pid: 0, name: "Alice", color: "white" }, { pid: 1, name: "Bob", color: "blue" } ] };
const timer = { pid: 0, remaining_ms: 47000, deadline_ms: 1047000, server_time_ms: 1000000, stage: "turn" };

test("host settings render actual policy and send a patch, while participant/in-match fields are read-only", () => {
  const sent = [], client = { youPid: 0, pendingSettings: { turn_timer: 90 }, setSettings: s => sent.push(s) };
  const host = render(MatchSettings, { client, room, connected: true });
  assert.equal(host.elements.find(e => e.type === "fieldset").disabled, false);
  assert.match(host.html, /Balanced|12 VP/);
  const select = host.elements.find(e => e.type === "select" && e.value === 90);
  select.onChange({ target: { value: "120" } });
  assert.deepEqual(sent, [{ turn_timer: 120 }]);
  for (const props of [{ client: { ...client, youPid: 1 }, room, connected: true },
    { client, room: { ...room, status: "in_match" }, connected: true }, { client, room, connected: false }]) {
    const view = render(MatchSettings, props);
    assert.equal(view.elements.find(e => e.type === "fieldset").disabled, true);
    assert.match(view.html, /read only/);
  }
});

test("color picker disables another player's color and submits only its own selection", () => {
  const sent = [], client = { youPid: 0, setColor: color => sent.push(color) };
  const view = render(PlayerColors, { client, room, connected: true });
  const choices = view.elements.filter(e => e.type === "button");
  assert.equal(choices.length, 6);
  assert.equal(choices.find(e => e["aria-label"] === "Choose blue").disabled, true);
  assert.equal(choices.find(e => e["aria-label"] === "Choose white")["aria-pressed"], true);
  choices.find(e => e["aria-label"] === "Choose orange").onClick();
  assert.deepEqual(sent, ["orange"]);
});

test("ownership color follows the public color independently of pid, including compact remapping and legacy fallback", () => {
  assert.equal(colorForPlayer(0, room.players), ROOM_COLORS.white);
  assert.equal(colorForPlayer(0, [{ pid: 0, color: "blue" }]), ROOM_COLORS.blue);
  assert.equal(colorForPlayer(4), "#a855f7");
  assert.equal(colorForPlayer(20, [{ pid: 20, color: "invalid" }]), "#ffffff");
});

test("HUD countdown interpolates authoritative remaining time and clamps at zero without local clock assumptions", () => {
  assert.equal(timerSeconds(timer), 47);
  assert.equal(timerSeconds(timer, 1250), 46);
  assert.equal(timerSeconds(timer, -9000), 47);
  assert.equal(timerSeconds(timer, 90000), 0);
  assert.equal(render(TurnTimer, { timer: null }).html, "");
  assert.match(render(TurnTimer, { timer }).html, /00:47/);
  assert.match(render(TurnTimer, { timer: { ...timer, remaining_ms: 9000 } }).html, /is-warning/);
  assert.match(render(TurnTimer, { timer: { ...timer, remaining_ms: 5000 } }).html, /is-urgent/);
  assert.match(render(TurnTimer, { timer: { ...timer, stage: "blocked", remaining_ms: 0 } }).html, /Action required/);
});

test("timer and authoritative colors appear only beside the current player in the compact HUD", () => {
  const state = { players: room.players.map(p => ({ ...p, vp: 2, resource_count: 3, dev_count: 0 })),
    turn: 1, turn_timer: { ...timer, pid: 1 }, rules_config: { target_vp: 12 } };
  const view = render(loaded.exports.PlayerStrip, { state, pid: 0 });
  assert.equal(view.elements.filter(e => e.className?.startsWith("turn-timer")).length, 1);
  assert.match(view.html, /--player-color:#f2f4f8/);
  assert.match(view.html, /00:47/);
});

test("chat renders ordered server history as escaped plain text, with input and empty/length constraints", () => {
  const messages = [{ id: 1, name: "<img>Alice", color: "orange", text: "<script>alert(1)</script>", sent_at_ms: 1000000 },
    { id: 2, name: "Bob", color: "blue", text: "second message", sent_at_ms: 1001000 }];
  const before = JSON.stringify(messages);
  const view = render(RoomChat, { messages, send() {} });
  assert.match(view.html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(view.html, /<script>|<img>/);
  assert.ok(view.html.indexOf("alert(1)") < view.html.indexOf("second message"));
  assert.equal(view.elements.find(e => e.type === "input").maxLength, 500);
  assert.equal(view.elements.find(e => e.type === "button").disabled, true);
  assert.equal(JSON.stringify(messages), before);
});

test("collapsible bank shows authoritative counts when supplied and only availability in Hidden mode", () => {
  const available = { wood: true, brick: false };
  const visible = render(BankSummary, { available, counts: { wood: 15, brick: 0, sheep: 12, wheat: 9, ore: 14 } });
  assert.match(visible.html, /aria-label="wood: 15"/);
  assert.match(visible.html, /Development deck hidden/);
  assert.match(visible.html, /<details[^>]* open/);
  const hidden = render(BankSummary, { available });
  assert.match(hidden.html, /quantities are hidden/);
  assert.doesNotMatch(hidden.html, /wood: 15/);
});
