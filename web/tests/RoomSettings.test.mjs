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
  entryPoints: [fileURLToPath(new URL("../src/components/RoomSettings.tsx", import.meta.url))],
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  external: ["react", "react/jsx-runtime"],
});
let selects;
const traced = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  if (type === "select") selects.set(props["aria-label"], props);
  return jsxRuntime[name](type, props, key);
}])) };
const loaded = { exports: {} };
new Script(`(function(require, module, exports) { ${compiled.outputFiles[0].text}\n})`)
  .runInThisContext()(name => name === "react/jsx-runtime" ? traced : require(name), loaded, loaded.exports);

function render(official = true, scenario = "heading_for_new_shores") {
  selects = new Map();
  const sent = [];
  const target = scenario === "the_four_islands" ? 13 : 14;
  const room = { status: "lobby", host_pid: 0, map_rules: { target_vp: official ? target : 10 },
    settings: { target_vp: official ? target : 12, discard_threshold: 7 },
    map_meta: official ? { official_scenario: scenario, required_players: 3 } : {} };
  const client = { youPid: 0, setSettings: patch => sent.push(patch) };
  const html = renderToStaticMarkup(React.createElement(loaded.exports.MatchSettings, { room, client, connected: true }));
  return { sent, selects, html };
}

test("official scenario locks victory and discard while retaining ordinary room options", () => {
  const view = render();
  assert.equal(view.selects.get("Target VP").value, 14);
  assert.equal(view.selects.get("Target VP").disabled, true);
  assert.equal(view.selects.get("Discard threshold").value, 7);
  assert.equal(view.selects.get("Discard threshold").disabled, true);
  assert.match(view.html, /official scenario fixes the victory target and discard threshold/);
  for (const label of ["Dice mode", "Turn timer", "Starting player", "Bank resource counts"])
    assert.notEqual(view.selects.get(label).disabled, true);
  view.selects.get("Turn timer").onChange({ target: { value: "60" } });
  assert.deepEqual(view.sent, [{ turn_timer: 60 }]);
});

test("custom and Base rooms keep editable victory and discard settings", () => {
  const view = render(false);
  assert.equal(view.selects.get("Target VP").disabled, false);
  assert.equal(view.selects.get("Discard threshold").disabled, false);
  view.selects.get("Target VP").onChange({ target: { value: "15" } });
  view.selects.get("Discard threshold").onChange({ target: { value: "9" } });
  assert.deepEqual(view.sent, [{ target_vp: 15 }, { discard_threshold: 9 }]);
  assert.doesNotMatch(view.html, /official scenario fixes/);
});

test("Four Islands uses its own locked target, not New Shores' 14 VP", () => {
  const view = render(true, "the_four_islands");
  assert.equal(view.selects.get("Target VP").value, 13);
  assert.equal(view.selects.get("Target VP").disabled, true);
  assert.equal(view.selects.get("Discard threshold").value, 7);
  assert.equal(view.selects.get("Discard threshold").disabled, true);
});
