import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";

const compiled = await build({ stdin: {
  contents: `export { default as NumberToken3D } from "./NumberToken3D";
    export { default as HexTile3D } from "./HexTile3D";
    export { FogHexVisual } from "./FogVisual";
    export { VisualResources } from "./VisualResources";
    export { threatAnchor } from "./threatMotion";`,
  resolveDir: fileURLToPath(new URL("../src/board3d/", import.meta.url)), loader: "tsx",
}, bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
external: ["react", "react/jsx-runtime", "@react-three/fiber"] });

let elements = [], printed = [], pips = [];
const loaded = { exports: {} }, require = createRequire(import.meta.url);
const runtime = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(name => [name, (type, props, key) => {
  elements.push({ type, props });
  // Real React components/hooks produce the Three props. SSR has no WebGL scene:
  // use harmless DOM carriers for captured intrinsics and for the Fog cover only.
  // Actual Fog meshes, depth and raycasts are covered separately in Chrome.
  if (type === loaded.exports.FogHexVisual)
    return jsxRuntime[name]("span", { "data-three": "fog-cover" }, key);
  return typeof type === "string"
    ? jsxRuntime[name]("span", { "data-three": type, children: props.children }, key)
    : jsxRuntime[name](type, props, key);
}])) };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  name => name === "react/jsx-runtime" ? runtime : require(name), loaded, loaded.exports);
const { NumberToken3D, HexTile3D, VisualResources, threatAnchor } = loaded.exports;

function render(Component, props) {
  elements = []; printed = []; pips = [];
  const previous = globalThis.document;
  globalThis.document = { createElement(name) {
    assert.equal(name, "canvas");
    const context = { fillText(text) { printed.push({ text, color: this.fillStyle }); },
      beginPath() {}, arc(...args) { pips.push(args); }, fill() {} };
    return { width: 0, height: 0, getContext(kind) { assert.equal(kind, "2d"); return context; } };
  } };
  try {
    const html = renderToStaticMarkup(React.createElement(VisualResources, null, React.createElement(Component, props)));
    return { html, elements: [...elements], printed: [...printed], pips: [...pips] };
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
}
function token(result) {
  const root = result.elements.find(({ type, props }) => type === "group"
    && props.userData?.number != null && props.userData?.tileIndex == null);
  assert(root, "the actual numbered badge was rendered");
  const base = result.elements.find(({ type, props }) => type === "mesh" && props.receiveShadow && props.geometry?.type === "CylinderGeometry");
  assert(base, "the actual board-token body is present");
  return { position: root.props.position, number: root.props.userData.number,
    radius: Math.max(base.props.geometry.parameters.radiusTop, base.props.geometry.parameters.radiusBottom)
      * Math.max(base.props.scale[0], base.props.scale[2]) };
}

test("the occupied badge separates from the unchanged robber footprint while remaining entirely inside its hex", () => {
  const ordinary = token(render(NumberToken3D, { number: 12 }));
  const occupied = token(render(NumberToken3D, { number: 12, robberClearance: true }));
  const robber = threatAnchor("robber", [0, 0, 0]), robberBaseRadius = .2;
  const distance = marker => Math.hypot(marker.position[0] - robber[0], marker.position[2] - robber[2]);
  assert(distance(ordinary) < ordinary.radius + robberBaseRadius, "reproduce overlapping ordinary-token and robber standing areas");
  assert(distance(occupied) > occupied.radius + robberBaseRadius + .05, "occupied badge leaves meaningful physical clearance");
  assert.equal(occupied.position[1], ordinary.position[1], "do not float the printed token");
  assert.equal(occupied.position[2], ordinary.position[2]);
  assert.equal(occupied.radius, ordinary.radius, "do not rescale badges globally");
  const innerApothem = .94 * Math.sqrt(3) / 2;
  for (let i = 0; i < 6; i++) {
    const angle = i * Math.PI / 3;
    assert(occupied.position[0] * Math.cos(angle) + occupied.position[2] * Math.sin(angle) + occupied.radius < innerApothem,
      "the whole disc must remain within all six playable hex sides");
  }
});

test("clearance preserves real printed numbers, probability dots, red accents and the terrain-readable depth policy", () => {
  for (const [number, dots] of [[2, 1], [6, 5], [8, 5], [12, 1]]) {
    const before = render(NumberToken3D, { number }), after = render(NumberToken3D, { number, robberClearance: true });
    assert.equal(token(after).number, number);
    assert.deepEqual(after.printed, before.printed, "the actual canvas label keeps its text and color");
    assert.equal(after.printed[0].text, String(number));
    assert.equal(after.pips.length, dots);
    assert.equal(after.printed[0].color, number === 6 || number === 8 ? "#b63831" : "#202c35");
    const label = after.elements.find(({ type }) => type === "meshBasicMaterial");
    assert.equal(label.props.depthTest, false, "numbers must not disappear behind mountains/wheat again");
    assert.equal(label.props.depthWrite, false);
  }
});

test("ending clearance restores the ordinary badge without affecting authoritative tile position, ID or click dispatch", () => {
  const tile = Object.freeze({ tileIndex: 29, position: Object.freeze([-2 * Math.sqrt(3), 0, 3]),
    terrain: "fields", number: 12, visibility: "revealed" });
  const original = JSON.stringify(tile), inspected = [];
  const props = { tile, hovered: false, legal: true, selected: false,
    onHover() {}, onInspect(id) { inspected.push(id); } };
  const before = render(HexTile3D, props);
  const occupied = render(HexTile3D, { ...props, robberClearance: true });
  const restored = render(HexTile3D, { ...props, robberClearance: false });
  assert.notDeepEqual(token(occupied).position, token(before).position);
  assert.deepEqual(token(restored), token(before));
  for (const result of [before, occupied, restored]) {
    const root = result.elements.find(({ type, props }) => type === "group" && props.onClick);
    assert.equal(root.props.position, tile.position);
    assert.equal(root.props.userData.tileIndex, 29);
    assert.equal(root.props.userData.legal, true);
    root.props.onClick({ delta: 0, stopPropagation() {} });
  }
  assert.deepEqual(inspected, [29, 29, 29]);
  assert.equal(JSON.stringify(tile), original);
});

test("even a malformed hidden Fog tile cannot construct a terrain or numbered badge when clearance is requested", () => {
  const inspected = [];
  const result = render(HexTile3D, { tile: { tileIndex: 29, position: [0, 0, 0],
    terrain: "fields", number: 12, visibility: "hidden" },
    hovered: false, legal: true, selected: true, robberClearance: true,
    onHover() {}, onInspect(id) { inspected.push(id); } });
  assert.match(result.html, /fog-cover/);
  assert(!result.elements.some(({ type }) => type === NumberToken3D));
  assert(!result.elements.some(({ props }) => props.userData?.terrainFallback || props.userData?.terrainAsset));
  assert.deepEqual(result.printed, []);
  const root = result.elements.find(({ type, props }) => type === "group" && props.onClick);
  assert.equal(root.props.userData.terrain, "fog");
  assert.equal(root.props.userData.number, null);
  assert.equal(root.props.userData.legal, false);
  root.props.onClick({ delta: 0, stopPropagation() {} });
  assert.deepEqual(inspected, []);
});
