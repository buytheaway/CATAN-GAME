import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import { PerspectiveCamera, Vector3 } from "three";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const compiled = await build({
  stdin: { contents: 'export * from "./board3d/model"; export * from "./board3d/coordinates"; export { hexCorners } from "./components/BoardView.utils"; export { default as BoardView } from "./components/BoardView";',
    resolveDir: fileURLToPath(new URL("../src/", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  external: ["react", "react/jsx-runtime"],
});
const loaded = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  createRequire(import.meta.url), loaded, loaded.exports);
const { createRenderModel, tilePosition, hexCorners, cameraFrame, cameraFootprint, portLabelPosition, BoardView } = loaded.exports;
const fixtures = JSON.parse(readFileSync(new URL("./fixtures/s2a-boards.json", import.meta.url)));
const close = (a, b) => assert(Math.abs(a - b) < 1e-8, `${a} != ${b}`);

for (const [preset, state] of Object.entries(fixtures)) {
  test(`${preset}: actual server centers and vertices agree with SVG and Three`, () => {
    const model = createRenderModel(state);
    assert.equal(model.tiles.length, 37);
    for (const [index, tile] of state.tiles.entries()) {
      assert.equal(model.tiles[index].tileIndex, index);
      assert.equal(model.tiles[index].terrain, tile.terrain);
      assert.equal(model.tiles[index].number, tile.number);
      const axial = tilePosition({ q: tile.q, r: tile.r }, state.size);
      close(model.tiles[index].position[0], axial[0]);
      close(model.tiles[index].position[2], axial[2]);
      const svg = hexCorners(...tile.center, state.size).split(" ").map(p => p.split(",").map(Number));
      const ids = new Set(state.edges.filter(e => state.edge_adj_hexes[e.join(",")].includes(index)).flat());
      const adjacentVertices = [...ids].filter(id => svg.some(c =>
        Math.hypot(c[0] - state.vertices[id][0], c[1] - state.vertices[id][1]) < 1e-8));
      assert.equal(adjacentVertices.length, 6);
    }
  });

  test(`${preset}: round port labels face their local water including inward coasts`, () => {
    const model = createRenderModel(state);
    assert.equal(model.ports.length, 9);
    for (const port of model.ports) {
      const land = state.edge_adj_hexes[port.edge.join(",")].filter(i => state.tiles[i].terrain !== "sea");
      assert.equal(land.length, 1);
      const center = model.tiles[land[0]].position;
      const label = portLabelPosition(port);
      assert((label[0] - port.anchor[0]) * (port.anchor[0] - center[0])
        + (label[2] - port.anchor[2]) * (port.anchor[2] - center[2]) > 0);
      close(port.anchor[0], (state.vertices[port.edge[0]][0] + state.vertices[port.edge[1]][0]) / 2 / state.size);
      assert.deepEqual(port.endpoints.map(p => [p[0], p[2]]), port.edge.map(v => state.vertices[v].map(n => n / state.size)));
    }
  });

  test(`${preset}: larger archipelago footprint fits desktop camera without preset positions`, () => {
    const model = createRenderModel(state), footprint = cameraFootprint(model);
    for (const [width, height] of [[1920, 1080], [1440, 900], [1280, 720]]) {
      const frame = cameraFrame(model.bounds, width / height, 38, footprint);
      const camera = new PerspectiveCamera(38, width / height, .01, frame.distance * 6);
      camera.position.set(...frame.position);
      camera.lookAt(...frame.target);
      camera.updateMatrixWorld();
      for (const point of footprint) {
        const projected = new Vector3(...point).project(camera);
        assert(Math.abs(projected.x) <= 1 && Math.abs(projected.y) <= 1);
      }
    }
  });

  test(`${preset}: original ownership IDs render pieces with no new game model`, () => {
    const edge = state.edges[0], key = edge.join(","), vertex = edge[0];
    const copy = { ...state, occupied_v: { [vertex]: [1, 2] }, occupied_e: { [key]: 0 }, occupied_ships: {} };
    const model = createRenderModel(copy);
    assert.equal(model.buildings[0].vertexId, vertex);
    assert.equal(model.buildings[0].level, 2);
    assert.equal(model.buildings[0].owner, 1);
    assert.deepEqual(model.roads[0].edge, edge);
    assert.equal(model.roads[0].owner, 0);
  });
}

test("offboard robber is omitted by both real SVG and 3D; any land remains selectable", () => {
  const state = { ...fixtures.seafarers_gold_haven, phase: "main", pending_action: "robber_move", pending_pid: 0, turn: 0 };
  const before = JSON.stringify(state);
  assert.equal(state.robber_tile, -1);
  assert.deepEqual(createRenderModel(state).robbers, []);
  const land = state.tiles.findIndex(t => t.terrain !== "sea");
  const interaction = { targets: { tiles: [land], vertices: [], edges: [] }, selection: { shipSource: null },
    onTileClick() {}, onVertexClick() {}, onEdgeClick() {} };
  const html = renderToStaticMarkup(React.createElement(BoardView, { state, interaction }));
  assert(html.includes(`data-target-tile="${land}"`));
  assert(!html.includes(`>R</text>`));
  assert.equal(JSON.stringify(state), before);
});
