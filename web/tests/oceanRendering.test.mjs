import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const compiled = await build({ stdin: {
  contents: 'export { createVisualResources } from "./resources"; export { BOARD_RIM_TOP, DECORATIVE_WATER_TOP, coastVisualPosition } from "./coordinates";',
  resolveDir: fileURLToPath(new URL("../src/board3d/", import.meta.url)), loader: "ts",
}, bundle: true, write: false, platform: "node", format: "esm" });
const { createVisualResources, BOARD_RIM_TOP, DECORATIVE_WATER_TOP, coastVisualPosition } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

test("shared ocean geometry follows the full pointy grid and visible terrain rim", () => {
  const pool = createVisualResources(); pool.retain();
  const geometry = pool.geometry("oceanHex");
  geometry.computeBoundingBox();
  assert(Math.abs(geometry.boundingBox.max.y - DECORATIVE_WATER_TOP) < 1e-6);
  const coastTop = coastVisualPosition([0, 0, 0])[1] + .05 / 2;
  assert.equal(coastTop, BOARD_RIM_TOP);
  assert(coastTop - geometry.boundingBox.max.y > .007,
    "water must stay below the overlapping coastal strip, not coplanar with its top");
  assert(Math.abs(geometry.boundingBox.min.y - (BOARD_RIM_TOP - .18)) < 1e-6,
    "lowering the surface keeps the original base above the frame skirt bottom");
  assert(Math.abs(geometry.boundingBox.max.z - 1) < 1e-6);
  assert(Math.abs(geometry.boundingBox.max.x - Math.sqrt(3) / 2) < 1e-6);
  assert.equal(geometry.groups.length, 2, "do not submit a hidden bottom cap");
  assert.equal(geometry.groups.reduce((sum, group) => sum + group.count / 3, 0), 18);
  const underlay = pool.geometry("oceanFill"); underlay.computeBoundingBox();
  assert(underlay.boundingBox.max.y < geometry.boundingBox.max.y, "gutter fill must not z-fight with water top");
  assert(Math.abs(underlay.boundingBox.max.z - 1) < 1e-6);
  pool.release();
});

test("ocean geometry/materials are shared across cells and live StrictMode leases", async () => {
  const pool = createVisualResources(); pool.retain();
  const body = pool.geometry("oceanHex"), fill = pool.geometry("oceanFill");
  const material = pool.standard("#ffffff"); let disposed = 0;
  for (const resource of [body, fill, material]) resource.addEventListener("dispose", () => disposed++);
  for (let i = 0; i < 100; i++) {
    assert.equal(pool.geometry("oceanHex"), body);
    assert.equal(pool.geometry("oceanFill"), fill);
    assert.equal(pool.standard("#ffffff"), material);
  }
  pool.release(); pool.retain(); await Promise.resolve();
  assert.equal(disposed, 0, "an immediate effect remount keeps resources alive");
  pool.release(); await Promise.resolve(); assert.equal(disposed, 3);
});
